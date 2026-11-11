"""Real HTTP + real LaBSE retrieval test. Does not send text to any LLM."""

import asyncio
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=600) as client:
        response = await client.post("/api/session")
        response.raise_for_status()
        try:
            for name in ("source-history.txt", "source-environment.txt"):
                response = await client.post(
                    "/api/sources/upload",
                    files={"file": (name, (ROOT / "fixtures" / name).read_bytes(), "text/plain")},
                )
                response.raise_for_status()
            query = (ROOT / "fixtures/suspicious.txt").read_text(encoding="utf-8")
            response = await client.post(
                "/api/reports/generate", json={"text": query, "preview_only": True}
            )
            response.raise_for_status()
            rid = response.json()["report_id"]
            stages = []
            async with client.stream("GET", f"/api/reports/{rid}/events") as stream:
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                        stages.append(event["stage"])
                        print(event["stage"], flush=True)
                        if event.get("terminal"):
                            break
            response = await client.get(f"/api/reports/{rid}/download")
            response.raise_for_status()
            result = response.json()
            assert result["preview_only"] and result["status"] == "partial"
            assert result["metadata"]["embedding_model"] == "sentence-transformers/LaBSE"
            assert result["total_source_documents"] == 2 and result["total_sentences"] == 4
            assert result["unverified_sentences"] == 4 and result["estimated_matched_coverage"] == 0
            assert any(c["cosine_similarity"] > 0.99 for c in result["matches"][0]["sources"])
            assert "Running LaBSE semantic retrieval" in stages
            assert "Running lexical retrieval and LCS reranking" in stages
            (ROOT / "artifacts").mkdir(exist_ok=True)
            (ROOT / "artifacts" / "retrieval-smoke.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "source_sentences": result["metadata"]["diagnostics"][
                            "indexed_source_sentences"
                        ],
                        "query_sentences": result["total_sentences"],
                        "candidate_pairs": sum(len(r["sources"]) for r in result["matches"]),
                        "processing_seconds": result["processing_seconds"],
                        "external_llm_calls": 0,
                    }
                )
            )
        finally:
            response = await client.delete("/api/session")
            response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
