import asyncio
import json
import time
import httpx
import pytest
from app import config
from app.main import create_app
from app.schemas import Verification

SOURCE_A = "বাংলাদেশের রাজধানী ঢাকা। ঘটনাটি ২০১০ সালে ঘটে। নদী বহমান।"
SOURCE_B = "বাংলাদেশের রাজধানী ঢাকা। গাছ আমাদের অক্সিজেন দেয়।"
QUERY = "বাংলাদেশের রাজধানী ঢাকা। ঘটনাটি ২০১২ সালে ঘটে।"


async def add_source(client, value=SOURCE_A, name="a.txt"):
    response = await client.post(
        "/api/sources/upload", files={"file": (name, value.encode(), "text/plain")}
    )
    assert response.status_code == 200, response.text
    return response.json()["source"]


async def configure(client, mode="hybrid"):
    response = await client.post(
        "/api/settings/openrouter",
        json={"model": "fixture/model", "api_key": "test-only-token", "mode": mode},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def await_report(client, report_id):
    for _ in range(250):
        response = await client.get("/api/reports/" + report_id)
        assert response.status_code == 200
        if "matches" in response.json():
            return response.json()
        await asyncio.sleep(0.01)
    raise AssertionError("Report did not finish.")


@pytest.fixture
def mocked_verifier(monkeypatch):
    calls = []

    async def verify(self, query, source):
        calls.append((query, source))
        relation = (
            "equivalent"
            if query == source
            else ("contradiction" if "২০১২" in query and "২০১০" in source else "unrelated")
        )
        return Verification(
            status="verified",
            relation=relation,
            reason="Deterministic fixture verdict.",
            actual_model="fixture/model",
            usage={"total_tokens": 10},
        )

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", verify)
    return calls


async def test_complete_pipeline_multi_source_and_progress(client, app, mocked_verifier):
    await add_source(client)
    await add_source(client, SOURCE_B, "b.txt")
    await configure(client)
    response = await client.post("/api/reports/generate", json={"text": QUERY})
    assert response.status_code == 202
    report_id = response.json()["report_id"]
    result = await await_report(client, report_id)
    assert result["status"] == "completed" and result["verification_complete"]
    assert result["matched_sentences"] == 1 and result["unmatched_sentences"] == 1
    assert result["matching_source_documents"] == 2
    assert result["estimated_matched_coverage"] == 42.86
    exact = [
        c for c in result["matches"][0]["sources"] if c["verification"]["relation"] == "equivalent"
    ]
    assert len(exact) == 2
    assert all(c["source"]["line_start"] == 1 for c in exact)
    assert result["metadata"]["verification_configuration"]["model"] == "fixture/model"
    assert "test-only-token" not in json.dumps(result)
    download = await client.get(f"/api/reports/{report_id}/download")
    assert download.json() == result and "attachment" in download.headers["content-disposition"]
    events = await client.get(f"/api/reports/{report_id}/events")
    assert "text/event-stream" in events.headers["content-type"]
    assert "terminal" in events.text and "Report ready" in events.text
    assert "Verifying candidates" in events.text
    resumed = await client.get(f"/api/reports/{report_id}/events", headers={"Last-Event-ID": "2"})
    assert "\nid: 1\n" not in resumed.text and not resumed.text.startswith("id: 1\n")
    assert len(mocked_verifier) < 2 * 5  # Identical content across sources is verified once.
    calls_before = len(mocked_verifier)
    second = await client.post("/api/reports/generate", json={"text": QUERY})
    again = await await_report(client, second.json()["report_id"])
    assert len(mocked_verifier) == calls_before
    assert again["metadata"]["diagnostics"]["cached_pairs"] > 0


async def test_preview_without_key_is_unverified(client):
    await add_source(client)
    denied = await client.post("/api/reports/generate", json={"text": QUERY})
    assert denied.status_code == 422
    started = await client.post("/api/reports/generate", json={"text": QUERY, "preview_only": True})
    result = await await_report(client, started.json()["report_id"])
    assert result["status"] == "partial" and result["preview_only"]
    assert result["estimated_matched_coverage"] == 0
    assert result["unverified_sentences"] == 2
    assert result["matches"][0]["sources"]


async def test_cross_session_isolation_and_secret_deletion(client, app, mocked_verifier):
    source = await add_source(client)
    await configure(client)
    started = await client.post("/api/reports/generate", json={"text": QUERY})
    report_id = started.json()["report_id"]
    await await_report(client, report_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as other:
        await other.post("/api/session")
        assert (await other.get("/api/sources")).json()["sources"] == []
        assert (await other.get("/api/settings")).json()["key_configured"] is False
        for path in [
            f"/api/sources/{source['document_id']}",
            f"/api/reports/{report_id}",
            f"/api/reports/{report_id}/download",
            f"/api/reports/{report_id}/events",
        ]:
            assert (await other.get(path)).status_code == 404
        assert (await other.delete("/api/sources/" + source["document_id"])).status_code == 404
        assert (await other.post(f"/api/reports/{report_id}/cancel")).status_code == 404
    assert (await client.delete("/api/settings/openrouter")).json()["key_configured"] is False
    assert (await client.delete("/api/session")).status_code == 200
    assert (await client.get("/api/sources")).status_code == 401
    assert not app.state.store.sessions or all(
        not s.sources for s in app.state.store.sessions.values()
    )


async def test_duplicate_and_source_removal_clears_embeddings(client, app):
    source = await add_source(client)
    duplicate = await client.post(
        "/api/sources/upload", files={"file": ("renamed.txt", SOURCE_A.encode())}
    )
    assert duplicate.json()["duplicate"]
    assert len((await client.get("/api/sources")).json()["sources"]) == 1
    started = await client.post("/api/reports/generate", json={"text": QUERY, "preview_only": True})
    await await_report(client, started.json()["report_id"])
    session = next(iter(app.state.store.sessions.values()))
    assert session.indexer.cache
    assert (await client.delete("/api/sources/" + source["document_id"])).status_code == 200
    assert session.indexer.cache == {}


async def test_uploaded_input_and_ambiguous_inputs(client):
    await add_source(client)
    uploaded = await client.post("/api/input/upload", files={"file": ("query.txt", QUERY.encode())})
    input_id = uploaded.json()["document_id"]
    assert uploaded.json()["sentences"][0]["char_start"] == 0
    bad = await client.post(
        "/api/reports/generate", json={"text": QUERY, "input_id": input_id, "preview_only": True}
    )
    assert bad.status_code == 422
    started = await client.post(
        "/api/reports/generate", json={"input_id": input_id, "preview_only": True}
    )
    result = await await_report(client, started.json()["report_id"])
    assert result["query_filename"] == "query.txt"
    assert (await client.delete("/api/input")).status_code == 200
    assert (
        await client.post(
            "/api/reports/generate", json={"input_id": input_id, "preview_only": True}
        )
    ).status_code == 404


async def test_missing_input_and_invalid_uploads(client):
    assert (
        await client.post("/api/reports/generate", json={"text": QUERY, "preview_only": True})
    ).status_code == 422
    await add_source(client)
    for body in ({"preview_only": True}, {"text": "   ", "preview_only": True}):
        assert (await client.post("/api/reports/generate", json=body)).status_code == 422
    for name, data in [("empty.txt", b""), ("wrong.exe", b"abc"), ("wrong.pdf", b"not PDF")]:
        result = await client.post("/api/sources/upload", files={"file": (name, data)})
        assert result.status_code == 422


async def test_failed_verification_partial_report(client, monkeypatch):
    async def failed(*args):
        return Verification(status="failed", reason="Provider unavailable.")

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", failed)
    await add_source(client)
    await configure(client)
    started = await client.post("/api/reports/generate", json={"text": QUERY})
    result = await await_report(client, started.json()["report_id"])
    assert result["status"] == "partial" and not result["verification_complete"]
    assert result["matched_sentences"] == 0 and result["unmatched_sentences"] == 0
    assert result["unverified_sentences"] == 2


async def test_cancel_and_concurrent_report_guard(client, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(*args):
        entered.set()
        await release.wait()
        return Verification(status="verified", relation="unrelated", reason="Fixture.")

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", slow)
    await add_source(client)
    await configure(client)
    first = await client.post("/api/reports/generate", json={"text": QUERY})
    rid = first.json()["report_id"]
    await asyncio.wait_for(entered.wait(), 2)
    assert (await client.post("/api/reports/generate", json={"text": QUERY})).status_code == 409
    assert (
        await client.post("/api/settings/openrouter", json={"model": "other/model"})
    ).status_code == 409
    assert (await client.post(f"/api/reports/{rid}/cancel")).status_code == 200
    release.set()
    result = await await_report(client, rid)
    assert (
        result["cancelled"]
        and result["status"] == "partial"
        and not result["verification_complete"]
    )


async def test_embedding_failure_retains_unverified_sentences(client, app):
    def fail(_):
        raise RuntimeError("Private text or secret must not be returned.")

    app.state.embeddings.encode = fail
    await add_source(client)
    first = await client.post("/api/reports/generate", json={"text": QUERY, "preview_only": True})
    result = await await_report(client, first.json()["report_id"])
    assert result["status"] == "failed" and result["unverified_sentences"] == 2
    assert "Private text" not in json.dumps(result)


async def test_session_expiration(client, app):
    session = next(iter(app.state.store.sessions.values()))
    await add_source(client)
    await configure(client)
    session.expires = time.time() - 1
    assert (await client.get("/api/settings")).status_code == 401
    assert not session.api_key and not session.sources and not session.indexer.cache


async def test_csrf_host_body_limits_and_no_secret_in_validation(client):
    rejected = await client.post("/api/session", headers={"Origin": "https://attacker.example"})
    assert rejected.status_code == 403
    assert (
        await client.get("/api/health", headers={"Host": "attacker.example"})
    ).status_code == 400
    assert (
        await client.post(
            "/api/input/analyze",
            content=b"{}",
            headers={"Content-Length": str(config.MAX_UPLOAD + 999999)},
        )
    ).status_code == 413
    bad = await client.post(
        "/api/settings/openrouter",
        json={
            "api_key": "must-not-echo-this",
            "model": "bad model with spaces",
            "parallel_requests": 999,
        },
    )
    assert bad.status_code == 422 and "must-not-echo-this" not in bad.text
    assert "no-store" in bad.headers["cache-control"]


async def test_lcs_mode_without_embedding_dependency(client, app, mocked_verifier):
    def fail(_):
        raise AssertionError("No embeddings should be computed in LCS-only mode.")

    app.state.embeddings.encode = fail
    await add_source(client)
    await configure(client, "lcs")
    started = await client.post("/api/reports/generate", json={"text": "বাংলাদেশের রাজধানী ঢাকা।"})
    result = await await_report(client, started.json()["report_id"])
    assert result["verification_complete"] and result["estimated_matched_coverage"] == 100
    assert result["metadata"]["embedding_model"] is None


async def test_settings_test_requires_key_and_reports_models_errors(client, monkeypatch):
    assert (await client.post("/api/settings/test")).status_code == 422
    await configure(client)

    async def bad(*args):
        return Verification(status="failed", reason="Model unavailable.")

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", bad)
    result = await client.post("/api/settings/test")
    assert result.json()["ok"] is False


async def test_text_counts_match_backend_segmenter(client):
    result = await client.post("/api/input/analyze", json={"text": "ডা. করিম এলেন। তিনি গেলেন!"})
    assert result.json() == {"word_count": 5, "sentence_count": 2}


async def test_bad_key_stops_remaining_provider_requests(client, monkeypatch):
    calls = []

    async def rejected(*args):
        calls.append(1)
        return Verification(
            status="failed", reason="Invalid key.", error_code="authentication", attempts=1
        )

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", rejected)
    await add_source(client)
    await configure(client)
    started = await client.post("/api/reports/generate", json={"text": QUERY})
    result = await await_report(client, started.json()["report_id"])
    assert len(calls) == 1
    assert result["status"] == "partial" and result["matched_sentences"] == 0
    assert any(
        c["verification"]["error_code"] == "provider_circuit_open"
        for r in result["matches"]
        for c in r["sources"]
    )


async def test_cancellation_interrupts_inflight_http_work(client, monkeypatch):
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", blocked)
    await add_source(client)
    await configure(client)
    started = await client.post("/api/reports/generate", json={"text": QUERY})
    rid = started.json()["report_id"]
    await asyncio.wait_for(entered.wait(), 2)
    await client.post(f"/api/reports/{rid}/cancel")
    result = await asyncio.wait_for(await_report(client, rid), 2)
    assert result["cancelled"] and result["unverified_sentences"] == 2


async def test_uncertain_pairs_still_mark_incomplete(client, monkeypatch):
    async def uncertain(*args):
        return Verification(
            status="verified", relation="uncertain", reason="Insufficient evidence."
        )

    monkeypatch.setattr("app.llm_verifier.OpenRouterVerifier.verify", uncertain)
    await add_source(client)
    await configure(client)
    started = await client.post("/api/reports/generate", json={"text": QUERY})
    result = await await_report(client, started.json()["report_id"])
    assert result["status"] == "partial" and result["unverified_sentences"] == 2
    assert result["unverified_candidate_pairs"] > 0
