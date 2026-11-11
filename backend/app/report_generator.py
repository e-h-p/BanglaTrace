import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import time
import httpx
from . import config
from .bangla_sentence_segmenter import SEGMENTER_VERSION
from .coverage_calculator import calculate_coverage
from .embedding_service import EmbeddingProvider
from .hybrid_ranker import dense_retrieve, lexical_retrieve, fuse_rankings
from .llm_verifier import create_verifier, PROVIDER_NAMES
from .schemas import Alignment, Document, Settings, Verification
from .session_store import Job, Session

PIPELINE_VERSION = "1.0.0"


async def generate_report(
    job: Job,
    session: Session,
    documents: list[Document],
    query_doc: Document,
    settings: Settings,
    key: str,
    provider: EmbeddingProvider,
    preview: bool,
    client_factory=httpx.AsyncClient,
):
    start = time.perf_counter()
    timings, rows, usage = {}, [], {}
    diagnostics = dict(
        indexed_source_sentences=sum(len(d.sentences) for d in documents),
        query_sentences=len(query_doc.sentences),
        dense_candidates=0,
        lexical_candidates=0,
        fused_candidates=0,
        llm_candidates=0,
        verified_equivalent_pairs=0,
        rejected_pairs=0,
        cached_pairs=0,
    )
    job.status = "running"
    job.emit("Source sentences ready", source_sentences=diagnostics["indexed_source_sentences"])

    async def stage(label, function, *args):
        if job.cancel.is_set():
            raise asyncio.CancelledError()
        job.emit(label)
        t = time.perf_counter()
        value = await asyncio.to_thread(function, *args)
        timings[label] = round(time.perf_counter() - t, 4)
        if job.cancel.is_set():
            raise asyncio.CancelledError()
        return value

    error = None
    try:
        # Create rows before expensive work so cancellation/failure still returns every query sentence.
        rows = [Alignment(query=q) for q in query_doc.sentences]
        index = await stage(
            "Building or loading the source index",
            session.indexer.build,
            documents,
            provider,
            settings.mode != "lcs",
        )
        for d in documents:
            d.status = "indexed" if settings.mode != "lcs" else "lexical index ready"
        vectors = (
            await stage(
                "Encoding suspicious sentences",
                provider.encode,
                [s.normalized_text for s in query_doc.sentences],
            )
            if settings.mode != "lcs"
            else None
        )
        dense = (
            await stage(
                "Running LaBSE semantic retrieval",
                lambda: [
                    dense_retrieve(index.vectors, vector, settings.dense_top_k)
                    for vector in vectors
                ],
            )
            if settings.mode != "lcs"
            else [[] for _ in rows]
        )
        lexical = (
            await stage(
                "Running lexical retrieval and LCS reranking",
                lambda: [
                    lexical_retrieve(
                        index,
                        row.query.normalized_text,
                        settings.lexical_prefilter_k,
                        settings.lexical_top_k,
                    )
                    for row in rows
                ],
            )
            if settings.mode != "dense"
            else [[] for _ in rows]
        )

        def retrieve():
            for i, row in enumerate(rows):
                row.sources, counts = fuse_rankings(
                    index,
                    row.query.normalized_text,
                    vectors[i] if vectors is not None else None,
                    settings,
                    dense[i],
                    lexical[i],
                )
                for src, dst in [
                    ("dense", "dense_candidates"),
                    ("lexical", "lexical_candidates"),
                    ("fused", "fused_candidates"),
                    ("selected", "llm_candidates"),
                ]:
                    diagnostics[dst] += counts[src]

        await stage("Selecting candidate matches", retrieve)
        pairs = [(row, candidate) for row in rows for candidate in row.sources]
        if not preview:
            t = time.perf_counter()
            verification_stage = (
                f"Verifying candidates with the {PROVIDER_NAMES[settings.provider]} LLM"
            )
            job.emit(verification_stage, completed=0, total=len(pairs))
            semaphore, completed, memo = asyncio.Semaphore(settings.parallel_requests), 0, {}
            stop_reason = None
            config_hash = sha256(
                json.dumps(settings.model_dump(), sort_keys=True).encode()
            ).hexdigest()
            async with client_factory() as client:
                verifier = create_verifier(client, settings, key)

                async def verify_pair(row, candidate):
                    nonlocal stop_reason
                    digest = sha256(
                        (
                            config_hash
                            + "\0"
                            + row.query.normalized_text
                            + "\0"
                            + candidate.source.normalized_text
                        ).encode()
                    ).hexdigest()
                    if digest in session.verify_cache:
                        diagnostics["cached_pairs"] += 1
                        return session.verify_cache[digest].model_copy(deep=True)
                    async with semaphore:
                        if job.cancel.is_set():
                            return Verification(
                                reason="Report cancelled before this pair was verified."
                            )
                        if stop_reason is not None:
                            return Verification(
                                status="failed",
                                reason=stop_reason,
                                error_code="provider_circuit_open",
                            )
                        verdict = await verifier.verify(
                            row.query.original_text, candidate.source.original_text
                        )
                        if verdict.error_code in ("authentication", "credits", "model_unavailable"):
                            stop_reason = verdict.reason
                        for k, v in verdict.usage.items():
                            usage[k] = usage.get(k, 0) + v
                        if verdict.status == "verified":
                            if len(session.verify_cache) < 20000:
                                session.verify_cache[digest] = verdict.model_copy(deep=True)
                        return verdict

                async def perform(row, candidate):
                    nonlocal completed
                    digest = (row.query.normalized_text, candidate.source.normalized_text)
                    if digest not in memo:
                        memo[digest] = asyncio.create_task(verify_pair(row, candidate))
                    candidate.verification = (await memo[digest]).model_copy(deep=True)
                    completed += 1
                    job.emit(
                        verification_stage,
                        completed=completed,
                        total=len(pairs),
                    )

                # Bound task allocation as well as HTTP concurrency. Workers consume a shared iterator.
                iterator = iter(pairs)

                async def worker():
                    for row, candidate in iterator:
                        if job.cancel.is_set():
                            break
                        await perform(row, candidate)

                workers = [asyncio.create_task(worker()) for _ in range(settings.parallel_requests)]
                cancel_wait = asyncio.create_task(job.cancel.wait())
                group = asyncio.gather(*workers)
                try:
                    done, _ = await asyncio.wait(
                        [group, cancel_wait], return_when=asyncio.FIRST_COMPLETED
                    )
                    if group in done:
                        await group
                    else:
                        group.cancel()
                        await asyncio.gather(group, return_exceptions=True)
                finally:
                    pending = workers + list(memo.values()) + [cancel_wait]
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    await asyncio.gather(group, return_exceptions=True)
            timings["LLM verification"] = round(time.perf_counter() - t, 4)
        else:
            job.emit("Retrieval preview — LLM verification skipped")
        job.emit("Mapping verified matches to source locations")
    except asyncio.CancelledError:
        job.cancel.set()
    except Exception:
        # No third-party exception text: it may include request bodies or secrets.
        error = "Processing failed. Check dependency installation, available RAM, model download connectivity and server diagnostics."
        job.emit("Processing failed", error=error)
    finally:
        # Empty candidate lists are conclusive only after retrieval finishes successfully.
        retrieval_done = "Selecting candidate matches" in timings
        job.emit("Calculating matched-text coverage")
        summary = calculate_coverage(rows)
        if not retrieval_done or preview or job.cancel.is_set():
            for row in rows:
                if not row.sources:
                    row.status = "unverified"
            summary["unmatched_sentences"] = sum(r.status == "unmatched" for r in rows)
            summary["unverified_sentences"] = sum(r.status == "unverified" for r in rows)
        failed_pairs = sum(c.verification.status != "verified" for r in rows for c in r.sources)
        uncertain_pairs = sum(
            c.verification.status == "verified" and c.verification.relation == "uncertain"
            for r in rows
            for c in r.sources
        )
        diagnostics["verified_equivalent_pairs"] = sum(
            c.verification.relation == "equivalent" and c.verification.status == "verified"
            for r in rows
            for c in r.sources
        )
        diagnostics["rejected_pairs"] = sum(
            c.verification.relation in ("contradiction", "unrelated")
            and c.verification.status == "verified"
            for r in rows
            for c in r.sources
        )
        partial = bool(
            error
            or job.cancel.is_set()
            or preview
            or failed_pairs
            or summary["unverified_sentences"]
        )
        job.status = "partial" if partial else "completed"
        if error and not retrieval_done:
            job.status = "failed"
        job.emit("Preparing the report")
        job.result = {
            "report_id": job.report_id,
            "status": job.status,
            "preview_only": preview,
            "cancelled": job.cancel.is_set(),
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processing_seconds": round(time.perf_counter() - start, 3),
            **summary,
            "verification_complete": not partial,
            "total_source_documents": len(documents),
            "unverified_candidate_pairs": failed_pairs + uncertain_pairs,
            "query_text": query_doc.text,
            "query_filename": query_doc.filename,
            "matches": [r.model_dump() for r in rows],
            "source_documents": [d.model_dump() for d in documents],
            "metadata": {
                "pipeline_version": PIPELINE_VERSION,
                "segmenter_version": SEGMENTER_VERSION,
                "embedding_model": provider.model_id if settings.mode != "lcs" else None,
                "embedding_revision": provider.revision if settings.mode != "lcs" else None,
                "embedding_resolved_commit": (
                    getattr(provider, "resolved_revision", None) if settings.mode != "lcs" else None
                ),
                "long_sentence_policy": "Mean pooling of normalized token-window embeddings; no silent truncation.",
                "verification_configuration": settings.model_dump(),
                "usage": usage,
                "actual_models": sorted(
                    {
                        c.verification.actual_model
                        for r in rows
                        for c in r.sources
                        if c.verification.actual_model
                    }
                ),
                "diagnostics": diagnostics,
                "stage_seconds": timings,
                "coverage_method": "100 × words in query sentences with at least one verified equivalent / all eligible query words. Count each query sentence once. Words are whitespace-delimited tokens containing a Unicode letter or number.",
                "disclaimer": "Text overlap is evidence for review, not proof of plagiarism or academic misconduct.",
            },
        }
        logging.getLogger("uvicorn.error").info(
            "Pipeline diagnostics: %s",
            json.dumps(
                {
                    "counts": diagnostics,
                    "stage_seconds": timings,
                    "usage": usage,
                    "processing_seconds": job.result["processing_seconds"],
                    "status": job.status,
                }
            ),
        )
        job.emit("Report ready", status=job.status, terminal=True)
