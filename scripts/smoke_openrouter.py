"""Optional, chargeable real provider test. Never prints credentials or provider bodies."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config
from app.llm_verifier import OpenRouterVerifier
from app.schemas import Settings
import httpx


async def main():
    if not config.ENV_KEY or not config.ENV_MODEL:
        raise SystemExit(
            "Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env first. This test makes two chargeable remote calls."
        )
    async with httpx.AsyncClient() as client:
        verifier = OpenRouterVerifier(client, Settings(model=config.ENV_MODEL), config.ENV_KEY)
        for name, query, source in [
            ("paraphrase", "ঢাকা বাংলাদেশের রাজধানী।", "বাংলাদেশের রাজধানী ঢাকা।"),
            ("numeric contradiction", "ঘটনাটি ২০১২ সালে ঘটে।", "ঘটনাটি ২০১০ সালে ঘটে।"),
        ]:
            result = await verifier.verify(query, source)
            print(json.dumps({"case": name, **result.model_dump()}, ensure_ascii=True))
            if result.status != "verified":
                raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
