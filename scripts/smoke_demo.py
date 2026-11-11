"""Exercise the running app's bundled library and key-free preview without model downloads."""

import json
from pathlib import Path
import re
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=20) as client:
        response = client.post("/api/session")
        response.raise_for_status()
        try:
            page = client.get("/")
            page.raise_for_status()
            assert "BanglaTrace" in page.text
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.text):
                client.get(asset).raise_for_status()
            font_css = client.get("/assets/moulik/fonts.css")
            font_css.raise_for_status()
            for font in re.findall(r"url\(([^)]+)\)", font_css.text):
                client.get("/assets/moulik/" + font).raise_for_status()
            library = client.get("/api/sources").json()["sources"]
            assert len(library) == 5 and all(d["built_in"] for d in library)
            settings = client.get("/api/settings").json()
            assert set(settings["provider_accounts"]) == {"openrouter", "openai", "anthropic"}
            result = client.post("/api/settings/provider", json={"mode": "lcs"})
            result.raise_for_status()
            text = (ROOT / "frontend/src/samples/suspect_essay.txt").read_text(encoding="utf-8")
            start = client.post("/api/reports/generate", json={"text": text, "preview_only": True})
            start.raise_for_status()
            report_id = start.json()["report_id"]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                response = client.get("/api/reports/" + report_id)
                response.raise_for_status()
                report = response.json()
                if "matches" in report:
                    break
                time.sleep(0.25)
            assert "matches" in report, "Preview did not complete."
            assert report["preview_only"] and not report["verification_complete"]
            assert report["error"] is None and report["estimated_matched_coverage"] == 0
            assert report["total_source_documents"] == 5
            assert report["metadata"]["embedding_model"] is None
            candidates = sum(len(row["sources"]) for row in report["matches"])
            assert candidates > 0
            exported = client.get(f"/api/reports/{report_id}/download")
            exported.raise_for_status()
            assert exported.json() == report
            summary = {
                "sources": len(library),
                "source_sentences": sum(d["sentence_count"] for d in library),
                "input_sentences": report["total_sentences"],
                "candidate_pairs": candidates,
                "provider_options": sorted(settings["provider_accounts"]),
                "preview_only": True,
                "model_downloads": False,
                "inference_calls": 0,
            }
            output = ROOT / "artifacts/demo-smoke.json"
            output.parent.mkdir(exist_ok=True)
            output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
        finally:
            client.delete("/api/session").raise_for_status()


if __name__ == "__main__":
    main()
