"""Provider transports with one strict verifier contract. Never log private bodies or keys."""

import asyncio
import json
import re
import httpx
from pydantic import ValidationError
from .schemas import Settings, Verdict, Verification
from . import config

BASE_URL = "https://openrouter.ai/api/v1"
PROVIDER_NAMES = {"openrouter": "OpenRouter", "openai": "OpenAI", "anthropic": "Claude"}


class ProviderError(ValueError):
    pass


def parse_verdict(content: str) -> Verdict:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        return Verdict.model_validate_json(content)
    except ValidationError:
        # Tolerate prose around a single valid object, never multiple conflicting answers.
        decoder, objects = json.JSONDecoder(), []
        for match in re.finditer(r"\{", content):
            try:
                obj, _ = decoder.raw_decode(content[match.start() :])
                if isinstance(obj, dict) and ("relation" in obj or "reason" in obj):
                    objects.append(obj)
            except ValueError:
                pass
        if len(objects) != 1:
            raise ValueError("Expected one structured verification response.")
        return Verdict.model_validate(objects[0])


class OpenRouterVerifier:
    provider_name = "OpenRouter"
    base_url = BASE_URL
    endpoint = "/chat/completions"

    def __init__(self, client: httpx.AsyncClient, settings: Settings, api_key: str):
        self.client, self.settings, self._key = client, settings, api_key

    async def models(self) -> list[dict]:
        if self.provider_name != "OpenRouter" and not self._key:
            raise ProviderError(f"Save a {self.provider_name} API key before loading models.")
        try:
            models, after = [], None
            for _ in range(20):
                params = (
                    {"limit": 100, **({"after_id": after} if after else {})}
                    if self.provider_name == "Claude"
                    else {}
                )
                response = await self.client.get(
                    self.base_url + "/models", params=params, headers=self._headers(), timeout=20
                )
                if response.status_code != 200:
                    raise ProviderError(
                        f"Could not load the {self.provider_name} model catalog. Check the API key and permissions."
                    )
                data = response.json()
                for model in data["data"]:
                    if not isinstance(model.get("id"), str):
                        continue
                    models.append(
                        {
                            "id": model["id"],
                            "name": model.get("name") or model.get("display_name") or model["id"],
                            "context_length": model.get("context_length")
                            or model.get("max_input_tokens"),
                            "supported_parameters": model.get("supported_parameters"),
                        }
                    )
                if self.provider_name != "Claude" or not data.get("has_more"):
                    break
                next_after = data.get("last_id")
                if not next_after or next_after == after:
                    break
                after = next_after
            return models
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError(
                f"The {self.provider_name} model catalog is unavailable. Manual model IDs are supported."
            ) from exc

    def _headers(self):
        return {
            **({"Authorization": "Bearer " + self._key} if self._key else {}),
            "Content-Type": "application/json",
            "X-Title": "BanglaPlag AI",
        }

    def _payload(self, query, source):
        return {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": self.settings.prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"suspicious_sentence": query, "source_sentence": source},
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }

    def _json_mode(self, payload):
        payload["response_format"] = {"type": "json_object"}

    def _remove_json_mode(self, payload):
        return payload.pop("response_format", None) is not None

    def _content(self, data):
        return data["choices"][0]["message"]["content"]

    def _usage(self, data):
        return data.get("usage") or {}

    async def verify(self, query: str, source: str) -> Verification:
        if not self._key or not self.settings.model:
            return Verification(
                reason=f"{self.provider_name} API key and model must be configured."
            )
        if len(query) + len(source) > config.MAX_PAIR_CHARS:
            return Verification(
                status="failed",
                reason="This sentence pair exceeds the configured verification character budget. Split unusually long sentences or increase MAX_PAIR_CHARS for a suitable model.",
            )
        payload = self._payload(query, source)
        if self.settings.json_mode:
            self._json_mode(payload)
        usage_total, actual_model = {}, None
        reason = "Verification could not be completed."
        # At most four requests, including JSON-mode/inference-parameter fallback.
        for attempt in range(1, 5):
            try:
                response = await self.client.post(
                    self.base_url + self.endpoint,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.settings.timeout_seconds,
                )
                status = response.status_code
                if status in (401, 403):
                    return Verification(
                        status="failed",
                        reason=f"{self.provider_name} rejected the API key or access permissions.",
                        attempts=attempt,
                        error_code="authentication",
                    )
                if status == 402:
                    return Verification(
                        status="failed",
                        reason=f"{self.provider_name} requires available account credits.",
                        attempts=attempt,
                        error_code="credits",
                    )
                if status in (400, 404, 422):
                    if self._remove_json_mode(payload):
                        reason = "Structured output was unavailable; retrying prompt-and-parse."
                        continue
                    if "temperature" in payload and status in (400, 422):
                        del payload["temperature"]
                        reason = "Retrying without the optional temperature parameter."
                        continue
                    return Verification(
                        status="failed",
                        reason="Model unavailable or request parameters unsupported. Check the model route and settings.",
                        attempts=attempt,
                        error_code="model_unavailable",
                    )
                if status == 429 or status >= 500:
                    reason = f"{self.provider_name} rate limited the request or the provider is temporarily unavailable."
                    if attempt < 4:
                        try:
                            delay = min(
                                10,
                                max(
                                    0,
                                    float(response.headers.get("retry-after", 2 ** (attempt - 1))),
                                ),
                            )
                        except ValueError:
                            delay = 2 ** (attempt - 1)
                        await asyncio.sleep(delay)
                        continue
                if status != 200:
                    return Verification(
                        status="failed",
                        reason=(
                            reason
                            if status == 429 or status >= 500
                            else f"{self.provider_name} rejected the verification request."
                        ),
                        attempts=attempt,
                    )
                data = response.json()
                usage = self._usage(data)
                # Keep only numeric usage; provider errors/raw outputs must not leak secrets/text.
                for k in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "cost",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                ):
                    if type(usage.get(k)) in (int, float):
                        usage_total[k] = usage_total.get(k, 0) + usage[k]
                actual_model = (
                    data.get("model").replace(self._key, "[redacted]")
                    if isinstance(data.get("model"), str)
                    else None
                )
                content = self._content(data)
                if not isinstance(content, str):
                    raise ValueError("No structured response.")
                verdict = parse_verdict(content)
                # Do not allow a provider/custom prompt to echo the configured secret into reports.
                verdict.reason = verdict.reason.replace(self._key, "[redacted]")
                return Verification(
                    status="verified",
                    relation=verdict.relation,
                    reason=verdict.reason,
                    usage=usage_total,
                    actual_model=actual_model,
                    attempts=attempt,
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                reason = (
                    f"{self.provider_name} verification timed out or the network is unavailable."
                )
            except (ValueError, ValidationError, KeyError, IndexError, TypeError):
                reason = "The model returned malformed or invalid verification JSON."
            except httpx.HTTPError:
                reason = f"{self.provider_name} transport failed."
            if attempt < 4:
                await asyncio.sleep(min(4, 2 ** (attempt - 1)))
        return Verification(
            status="failed", reason=reason, usage=usage_total, actual_model=actual_model, attempts=4
        )


class OpenAIVerifier(OpenRouterVerifier):
    provider_name = "OpenAI"
    base_url = "https://api.openai.com/v1"
    endpoint = "/responses"

    def _headers(self):
        return {"Authorization": "Bearer " + self._key, "Content-Type": "application/json"}

    def _payload(self, query, source):
        return {
            "model": self.settings.model,
            "instructions": self.settings.prompt,
            "input": json.dumps(
                {"suspicious_sentence": query, "source_sentence": source}, ensure_ascii=False
            ),
            "temperature": self.settings.temperature,
            "max_output_tokens": self.settings.max_tokens,
            "store": False,
        }

    def _json_mode(self, payload):
        payload["text"] = {"format": {"type": "json_object"}}

    def _remove_json_mode(self, payload):
        return payload.pop("text", None) is not None

    def _content(self, data):
        if data.get("status") != "completed":
            raise ValueError("Response did not complete.")
        return "".join(
            part["text"]
            for item in data["output"]
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )

    def _usage(self, data):
        usage = data.get("usage") or {}
        return {
            "prompt_tokens": usage.get("input_tokens"),
            "completion_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }


class ClaudeVerifier(OpenRouterVerifier):
    provider_name = "Claude"
    base_url = "https://api.anthropic.com/v1"
    endpoint = "/messages"

    def _headers(self):
        return {
            "x-api-key": self._key,
            "anthropic-version": "2026-10-21",
            "Content-Type": "application/json",
        }

    def _payload(self, query, source):
        return {
            "model": self.settings.model,
            "system": self.settings.prompt,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {"suspicious_sentence": query, "source_sentence": source},
                        ensure_ascii=False,
                    ),
                }
            ],
            "max_tokens": self.settings.max_tokens,
        }

    def _json_mode(self, payload):
        # The same strict JSON instruction/parser is used; no OpenAI-specific parameters.
        pass

    def _content(self, data):
        if data.get("stop_reason") != "end_turn":
            raise ValueError("Response did not complete.")
        return "".join(part["text"] for part in data["content"] if part.get("type") == "text")

    def _usage(self, data):
        usage = data.get("usage") or {}
        result = {
            "prompt_tokens": usage.get("input_tokens"),
            "completion_tokens": usage.get("output_tokens"),
        }
        if all(type(usage.get(k)) in (int, float) for k in ("input_tokens", "output_tokens")):
            result["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
        for key in ("cache_read_input_tokens", "cache_creation_input_tokens"):
            if key in usage:
                result[key] = usage[key]
        return result


def create_verifier(client, settings, api_key):
    verifier = {
        "openrouter": OpenRouterVerifier,
        "openai": OpenAIVerifier,
        "anthropic": ClaudeVerifier,
    }[settings.provider]
    return verifier(client, settings, api_key)
