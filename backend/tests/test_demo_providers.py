import asyncio
import json

import httpx
import pytest

from app import config
from app.demo_library import load_demo_documents
from app.llm_verifier import create_verifier
from app.main import create_app
from app.schemas import Settings


def provider_response(provider, relation="equivalent"):
    text = json.dumps({"relation": relation, "reason": "Same central proposition."})
    if provider == "openai":
        return {
            "status": "completed",
            "model": "fixture-gpt",
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [{"type": "output_text", "text": text}]},
            ],
            "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
        }
    if provider == "anthropic":
        return {
            "stop_reason": "end_turn",
            "model": "fixture-claude",
            "content": [
                {"type": "thinking", "thinking": "ignored"},
                {"type": "text", "text": text},
            ],
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }
    return {
        "model": "fixture/router",
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }


@pytest.mark.parametrize(
    "provider,host,path",
    [
        ("openrouter", "openrouter.ai", "/api/v1/chat/completions"),
        ("openai", "api.openai.com", "/v1/responses"),
        ("anthropic", "api.anthropic.com", "/v1/messages"),
    ],
)
async def test_provider_transport_preserves_contract(provider, host, path):
    def handler(request):
        assert request.url.host == host and request.url.path == path
        body = json.loads(request.content)
        assert body["model"] == "fixture-model"
        if provider == "anthropic":
            assert request.headers["x-api-key"] == "fixture-key"
            assert request.headers["anthropic-version"] == "2026-10-21"
            assert "authorization" not in request.headers
            assert "temperature" not in body and "response_format" not in body
            assert body["system"] == settings.prompt and body["max_tokens"] == 300
            text = body["messages"][0]["content"]
        elif provider == "openai":
            assert request.headers["authorization"] == "Bearer fixture-key"
            assert "x-api-key" not in request.headers
            assert body["store"] is False and body["max_output_tokens"] == 300
            assert body["instructions"] == settings.prompt
            assert body["text"]["format"]["type"] == "json_object"
            text = body["input"]
        else:
            assert request.headers["authorization"] == "Bearer fixture-key"
            assert body["response_format"] == {"type": "json_object"}
            text = body["messages"][1]["content"]
        assert json.loads(text) == {
            "suspicious_sentence": "ঘটনাটি ২০১২ সালে ঘটে।",
            "source_sentence": "ঘটনাটি ২০১০ সালে ঘটে।",
        }
        return httpx.Response(200, json=provider_response(provider, "contradiction"))

    settings = Settings(provider=provider, model="fixture-model", json_mode=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await create_verifier(client, settings, "fixture-key").verify(
            "ঘটনাটি ২০১২ সালে ঘটে।", "ঘটনাটি ২০১০ সালে ঘটে।"
        )
    assert verdict.status == "verified" and verdict.relation == "contradiction"
    assert verdict.usage["total_tokens"] == 30 and "cost" not in verdict.usage


async def test_openai_optional_parameters_fallback(monkeypatch):
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "text" in body or "temperature" in body:
            return httpx.Response(400, json={"error": "unsupported optional parameter"})
        return httpx.Response(200, json=provider_response("openai"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await create_verifier(
            client, Settings(provider="openai", model="test", json_mode=True), "key"
        ).verify("a", "b")
    assert result.status == "verified" and len(bodies) == 3
    assert all(b["store"] is False for b in bodies)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_direct_provider_failure_and_secret_redaction(provider):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, json={"error": "private-key must never appear"})
        )
    ) as client:
        result = await create_verifier(
            client, Settings(provider=provider, model="test"), "private-key"
        ).verify("a", "b")
    assert result.status == "failed" and result.attempts == 1 and result.relation is None
    assert "private-key" not in result.reason


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_incomplete_direct_response_is_never_verified(provider, monkeypatch):
    async def immediate(_):
        pass

    monkeypatch.setattr("app.llm_verifier.asyncio.sleep", immediate)
    data = provider_response(provider)
    data["status" if provider == "openai" else "stop_reason"] = (
        "incomplete" if provider == "openai" else "max_tokens"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        result = await create_verifier(
            client, Settings(provider=provider, model="test"), "key"
        ).verify("a", "b")
    assert result.status == "failed" and result.relation is None and result.attempts == 4
    assert result.usage["total_tokens"] == 120


async def test_provider_credentials_models_catalog_and_clear_are_isolated(client, app, monkeypatch):
    monkeypatch.setitem(config.ENV_KEYS, "openrouter", "router-env-only")
    for provider, key, model in [
        ("openrouter", "router-key", "router/model"),
        ("openai", "openai-key", "gpt-fixture"),
        ("anthropic", "claude-key", "claude-fixture"),
    ]:
        before = await client.post(
            "/api/settings/provider", json={"provider": provider, "model": model}
        )
        if provider != "openrouter":
            assert before.json()["key_configured"] is False
            assert (await client.post("/api/settings/test")).status_code == 422
        saved = await client.post(
            "/api/settings/provider", json={"provider": provider, "model": model, "api_key": key}
        )
        assert saved.json()["key_configured"] and key not in saved.text
    session = next(iter(app.state.store.sessions.values()))
    assert session.key == "claude-key"
    switched = await client.post(
        "/api/settings/provider", json={"provider": "openai", "model": "gpt-fixture"}
    )
    assert session.key == "openai-key"
    assert switched.json()["provider_accounts"]["openrouter"]["model"] == "router/model"
    cleared = await client.delete("/api/settings/provider")
    assert not cleared.json()["key_configured"]
    assert (
        session.key_for("anthropic") == "claude-key"
        and session.key_for("openrouter") == "router-key"
    )
    await client.delete("/api/session")
    assert not session.api_keys and not session.provider_models
    assert all(not session.key_for(p) for p in config.ENV_KEYS)


@pytest.mark.parametrize("provider", ["openrouter", "openai", "anthropic"])
async def test_full_pipeline_uses_selected_provider_and_catalog(embeddings, provider):
    requests = []

    def handler(request):
        requests.append(request)
        expected_host = {
            "openrouter": "openrouter.ai",
            "openai": "api.openai.com",
            "anthropic": "api.anthropic.com",
        }[provider]
        assert request.url.host == expected_host
        assert (
            request.headers.get("x-api-key") == "selected-key"
            if provider == "anthropic"
            else request.headers["authorization"] == "Bearer selected-key"
        )
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "fixture-model", "display_name": "Fixture model"}],
                    "has_more": False,
                },
            )
        return httpx.Response(200, json=provider_response(provider))

    application = create_app(
        embeddings,
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        enable_demo_library=False,
    )
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            await client.post("/api/session")
            await client.post(
                "/api/settings/provider",
                json={
                    "provider": provider,
                    "model": "fixture-model",
                    "api_key": "selected-key",
                    "mode": "lcs",
                },
            )
            models = await client.get("/api/settings/models")
            assert models.json()["models"][0]["id"] == "fixture-model"
            assert (await client.post("/api/settings/test")).json()["ok"]
            text = "বাংলাদেশের নদীগুলো কৃষিকাজের জন্য পানি সরবরাহ করে।"
            await client.post("/api/sources/upload", files={"file": ("source.txt", text.encode())})
            started = await client.post("/api/reports/generate", json={"text": text})
            for _ in range(200):
                report = (await client.get("/api/reports/" + started.json()["report_id"])).json()
                if "matches" in report:
                    break
                await asyncio.sleep(0.01)
            assert report["verification_complete"] and report["estimated_matched_coverage"] == 100
            assert report["metadata"]["verification_configuration"]["provider"] == provider
            assert "selected-key" not in json.dumps(report)


async def test_demo_library_is_ready_previewable_and_copied_per_session(embeddings):
    application = create_app(embeddings, enable_demo_library=True)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            await client.post("/api/session")
            library = (await client.get("/api/sources")).json()["sources"]
            assert len(library) == 5 and all(d["built_in"] for d in library)
            source = (await client.get("/api/sources/" + library[0]["document_id"])).json()
            assert source["text"] and source["sentences"]
            assert (await client.delete("/api/sources/" + source["document_id"])).status_code == 400
            await client.post("/api/session")
            assert len((await client.get("/api/sources")).json()["sources"]) == 5
            await client.post("/api/settings/provider", json={"mode": "lcs"})
            start = await client.post(
                "/api/reports/generate",
                json={"text": source["sentences"][-1]["original_text"], "preview_only": True},
            )
            for _ in range(200):
                report = (await client.get("/api/reports/" + start.json()["report_id"])).json()
                if "matches" in report:
                    break
                await asyncio.sleep(0.01)
            assert report["preview_only"] and report["matches"][0]["sources"]
            assert report["total_source_documents"] == 5
            first_session = next(iter(application.state.store.sessions.values()))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://testserver"
            ) as second:
                await second.post("/api/session")
                second_session = list(application.state.store.sessions.values())[-1]
                assert (
                    first_session.sources[source["document_id"]]
                    is not second_session.sources[source["document_id"]]
                )
                await second.delete("/api/session")
            await client.delete("/api/session")
    assert len(load_demo_documents()) == 5
