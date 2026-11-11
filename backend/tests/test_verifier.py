import json
import httpx
import pytest
from app.llm_verifier import OpenRouterVerifier, parse_verdict
from app.schemas import Settings


@pytest.mark.parametrize(
    "value",
    [
        '{"relation":"equivalent","reason":"Same meaning."}',
        '```json\n{"relation":"partial","reason":"Some overlap."}\n```',
        'Answer: {"relation":"contradiction","reason":"Changed year."} End.',
    ],
)
def test_parse_valid(value):
    assert parse_verdict(value).relation in ("equivalent", "partial", "contradiction")


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        "no",
        '{"relation":"yes","reason":"x"}',
        '{"relation":"equivalent"}',
        '{"relation":"equivalent","reason":1}',
        '{"relation":"equivalent","reason":"x","id":"invented"}',
        '{"relation":"equivalent","reason":"x"} {"relation":"unrelated","reason":"y"}',
    ],
)
def test_parse_invalid(value):
    with pytest.raises(ValueError):
        parse_verdict(value)


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    async def immediate(_):
        pass

    monkeypatch.setattr("app.llm_verifier.asyncio.sleep", immediate)


async def test_contradiction_preserved():
    def handler(request):
        body = json.loads(request.content)
        assert "২০১০" in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "model": "returned/model",
                "choices": [
                    {
                        "message": {
                            "content": '{"relation":"contradiction","reason":"The year changed."}'
                        }
                    }
                ],
                "usage": {"total_tokens": 32, "cost": 0.001},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await OpenRouterVerifier(
            client, Settings(model="requested/model"), "fixture-token"
        ).verify("ঘটনাটি ২০১০ সালে ঘটে।", "ঘটনাটি ২০১২ সালে ঘটে।")
    assert verdict.status == "verified" and verdict.relation == "contradiction"
    assert verdict.actual_model == "returned/model" and verdict.usage["total_tokens"] == 32


async def test_unsupported_json_mode_fallback():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "Unsupported JSON mode"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"relation":"unrelated","reason":"Different facts."}'}}
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await OpenRouterVerifier(
            client, Settings(model="a/b", json_mode=True), "fixture-token"
        ).verify("a", "b")
    assert verdict.relation == "unrelated" and len(requests) == 2
    assert "response_format" not in requests[1]


@pytest.mark.parametrize(
    "status,attempts", [(401, 1), (403, 1), (402, 1), (404, 1), (429, 4), (503, 4)]
)
async def test_provider_failures_do_not_become_labels(status, attempts):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "private provider detail"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        v = await OpenRouterVerifier(client, Settings(model="a/b"), "fixture-token").verify(
            "a", "b"
        )
    assert v.status == "failed" and v.relation is None and len(calls) == attempts
    assert "private provider detail" not in v.reason


async def test_malformed_output_and_usage():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "not JSON"}}],
                    "usage": {"total_tokens": 5},
                },
            )
        )
    ) as client:
        verdict = await OpenRouterVerifier(client, Settings(model="a/b"), "fixture-token").verify(
            "a", "b"
        )
    assert (
        verdict.status == "failed"
        and verdict.relation is None
        and verdict.usage["total_tokens"] == 20
    )


async def test_network_timeout():
    def handler(request):
        raise httpx.ReadTimeout("private details", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await OpenRouterVerifier(client, Settings(model="a/b"), "fixture-token").verify(
            "a", "b"
        )
    assert verdict.status == "failed" and "timed out" in verdict.reason


async def test_missing_key_no_requests():
    def handler(_):
        raise AssertionError("Must not contact the provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        v = await OpenRouterVerifier(client, Settings(model="a/b"), "").verify("a", "b")
    assert v.status == "unverified"
