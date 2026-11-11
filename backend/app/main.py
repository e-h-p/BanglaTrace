import asyncio
from contextlib import asynccontextmanager
from hashlib import sha256
import json
import secrets
import time
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import config
from .bangla_sentence_segmenter import segment, words
from .document_parser import parse_document, DocumentError
from .embedding_service import LaBSEEmbeddings
from .llm_verifier import create_verifier, ProviderError
from .demo_library import load_demo_documents
from .report_generator import generate_report
from .schemas import Settings, SettingsUpdate, GenerateRequest, Document
from .session_store import SessionStore, Session, Job
import httpx


class BodyLimitMiddleware:
    """Limit streamed bodies too, before multipart spooling or JSON parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = config.MAX_UPLOAD + 256 * 1024
        headers = dict(scope.get("headers", []))
        try:
            too_big = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            too_big = True
        if too_big:
            return await JSONResponse(
                {
                    "error": {
                        "code": "upload_too_large",
                        "message": "Request exceeds the upload size limit.",
                    }
                },
                413,
            )(scope, receive, send)
        consumed, started = 0, False

        class TooLarge(Exception):
            pass

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                raise TooLarge()
            return message

        async def track_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, track_send)
        except TooLarge:
            if not started:
                await JSONResponse(
                    {
                        "error": {
                            "code": "upload_too_large",
                            "message": "Request exceeds the upload size limit.",
                        }
                    },
                    413,
                )(scope, receive, send)


def create_app(embedding_provider=None, verifier_client_factory=None, enable_demo_library=None):
    include_demo = (
        config.ENABLE_DEMO_LIBRARY if enable_demo_library is None else enable_demo_library
    )
    demo_documents = load_demo_documents() if include_demo else []
    store = SessionStore(demo_documents)
    client_factory = verifier_client_factory or httpx.AsyncClient
    local_hosts = {"localhost", "127.0.0.1", "testserver"}
    if set(config.ALLOWED_HOSTS) - local_hosts:
        if not config.SECURE_COOKIE or __import__("os").getenv("ALLOW_REMOTE_DEPLOYMENT") != "true":
            raise RuntimeError(
                "Remote deployment requires COOKIE_SECURE=true and ALLOW_REMOTE_DEPLOYMENT=true, with an authenticated HTTPS reverse proxy. See README."
            )

    @asynccontextmanager
    async def lifespan(app):
        async def cleanup():
            while True:
                await asyncio.sleep(30)
                store.prune()

        cleanup_task = asyncio.create_task(cleanup())
        yield
        cleanup_task.cancel()
        tasks = [j.task for s in store.sessions.values() for j in s.jobs.values() if j.task]
        for session in list(store.sessions.values()):
            session.dispose()
        await asyncio.gather(cleanup_task, *tasks, return_exceptions=True)

    app = FastAPI(title="BanglaPlag AI", version="1.0.0", lifespan=lifespan)
    app.state.store = store
    app.state.embeddings = embedding_provider or LaBSEEmbeddings()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.url.path.startswith("/api") and request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            allowed = config.ALLOWED_ORIGINS
            if (origin and origin not in allowed) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return JSONResponse(
                    {
                        "error": {
                            "code": "origin_rejected",
                            "message": "This request origin is not allowed.",
                        }
                    },
                    403,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"error": {"code": str(exc.status_code), "message": exc.detail}},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default errors include submitted input, which can contain the API key.
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request. Check field values and supported limits.",
                    "fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An internal processing error occurred.",
                }
            },
            500,
        )

    def current_session(request: Request):
        session = store.get(request.cookies.get(config.COOKIE))
        if not session:
            raise HTTPException(
                401, "Your session expired. Reload the application to create a new workspace."
            )
        now = time.time()
        session.request_times = [t for t in session.request_times if now - t < 60]
        if len(session.request_times) >= 180:
            raise HTTPException(429, "Too many requests. Wait a moment and try again.")
        session.request_times.append(now)
        return session

    def active(session):
        return any(j.status in ("queued", "running") for j in session.jobs.values())

    def ensure_idle(session):
        if active(session):
            raise HTTPException(
                409, "Wait for or cancel the active report before changing sources or settings."
            )

    def summary(document):
        return {
            **document.model_dump(exclude={"text", "sentences"}),
            "sentence_count": len(document.sentences),
        }

    def public_settings(session):
        return {
            **session.settings.model_dump(),
            "key_configured": bool(session.key),
            "key_source": (
                "session" if session.api_key else ("environment" if session.key else None)
            ),
            "expires_at": session.expires,
            "provider_accounts": {
                provider: {
                    "key_configured": bool(session.key_for(provider)),
                    "key_source": (
                        "session"
                        if session.api_keys.get(provider)
                        else ("environment" if session.key_for(provider) else None)
                    ),
                    "model": (
                        session.settings.model
                        if provider == session.settings.provider
                        else (
                            session.provider_models.get(
                                provider, config.ENV_MODELS.get(provider, "")
                            )
                        )
                    ),
                }
                for provider in config.ENV_KEYS
            },
        }

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "embedding_model": config.MODEL}

    @app.post("/api/session")
    async def init_session(request: Request):
        session = store.get(request.cookies.get(config.COOKIE))
        if not session:
            try:
                session = store.create()
            except ValueError as exc:
                raise HTTPException(503, str(exc))
        response = JSONResponse(
            {
                "expires_at": session.expires,
                "limits": {
                    "max_upload_mb": config.MAX_UPLOAD // 1024**2,
                    "max_sources": config.MAX_SOURCES,
                    "max_query_sentences": config.MAX_QUERY_SENTENCES,
                    "max_source_sentences": config.MAX_SOURCE_SENTENCES,
                },
                "settings": public_settings(session),
            }
        )
        response.set_cookie(
            config.COOKIE,
            session.token,
            httponly=True,
            secure=config.SECURE_COOKIE,
            samesite="strict",
            max_age=max(1, int(session.expires - time.time())),
            path="/",
        )
        return response

    @app.delete("/api/session")
    async def clear_session(session: Session = Depends(current_session)):
        tasks = [j.task for j in session.jobs.values() if j.task and not j.task.done()]
        store.delete(session.token)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        response = JSONResponse({"cleared": True})
        response.delete_cookie(config.COOKIE, path="/")
        return response

    @app.get("/api/settings")
    async def settings(session: Session = Depends(current_session)):
        return public_settings(session)

    @app.post("/api/settings/openrouter")
    @app.post("/api/settings/provider")
    async def save_settings(body: SettingsUpdate, session: Session = Depends(current_session)):
        ensure_idle(session)
        key = None
        if body.api_key is not None:
            key = body.api_key.get_secret_value().strip()
            if not key or len(key) > 512 or any(c.isspace() for c in key):
                raise HTTPException(422, "The API key must be a nonempty token without whitespace.")
        session.provider_models[session.settings.provider] = session.settings.model
        session.settings = Settings.model_validate(body.model_dump(exclude={"api_key"}))
        session.provider_models[session.settings.provider] = session.settings.model
        if key is not None:
            session.api_key = key
            session.use_env_key = False
            session.verify_cache.clear()
        return public_settings(session)

    @app.delete("/api/settings/openrouter")
    @app.delete("/api/settings/provider")
    async def clear_key(session: Session = Depends(current_session)):
        ensure_idle(session)
        session.api_key, session.use_env_key = "", False
        session.verify_cache.clear()
        return public_settings(session)

    @app.get("/api/settings/models")
    async def models(session: Session = Depends(current_session)):
        # Explicit UI action only; never automatically called on page load.
        async with client_factory() as client:
            try:
                return {
                    "models": await create_verifier(client, session.settings, session.key).models()
                }
            except ProviderError as exc:
                raise HTTPException(502, str(exc))

    @app.post("/api/settings/test")
    async def test_connection(session: Session = Depends(current_session)):
        ensure_idle(session)
        if not session.key or not session.settings.model:
            raise HTTPException(422, "Save an API key and model first.")
        async with client_factory() as client:
            verifier = create_verifier(client, session.settings, session.key)
            verdict = await verifier.verify("বাংলাদেশের রাজধানী ঢাকা।", "ঢাকা বাংলাদেশের রাজধানী।")
        return {
            "ok": verdict.status == "verified",
            "verification": verdict.model_dump(),
            "message": (
                "Connection succeeded; the model returned valid structured verification."
                if verdict.status == "verified"
                else verdict.reason
            ),
        }

    @app.get("/api/sources")
    async def sources(session: Session = Depends(current_session)):
        return {"sources": [summary(d) for d in session.sources.values()]}

    async def read_upload(file):
        try:
            data = await file.read(config.MAX_UPLOAD + 1)
            if len(data) > config.MAX_UPLOAD:
                raise HTTPException(413, "File exceeds the upload size limit.")
            return data
        finally:
            await file.close()

    @app.post("/api/sources/upload")
    async def upload_source(file: UploadFile, session: Session = Depends(current_session)):
        async with session.upload_lock:
            ensure_idle(session)
            data = await read_upload(file)
            digest = sha256(data).hexdigest()
            existing = next((d for d in session.sources.values() if d.content_hash == digest), None)
            if existing:
                return {"source": summary(existing), "duplicate": True}
            if len(session.sources) >= config.MAX_SOURCES:
                raise HTTPException(422, "Source document limit reached.")
            if (
                sum(d.size_bytes for d in session.sources.values()) + len(data)
                > config.MAX_SESSION_BYTES
            ):
                raise HTTPException(422, "Session upload storage limit reached.")
            try:
                doc = await asyncio.to_thread(parse_document, data, file.filename or "upload")
            except DocumentError as exc:
                raise HTTPException(422, str(exc))
            if (
                sum(len(d.sentences) for d in session.sources.values()) + len(doc.sentences)
                > config.MAX_SOURCE_SENTENCES
            ):
                raise HTTPException(422, "Total source sentence limit reached.")
            ensure_idle(session)
            session.sources[doc.document_id] = doc
            return {"source": summary(doc), "duplicate": False}

    @app.get("/api/sources/{document_id}")
    async def source_preview(document_id: str, session: Session = Depends(current_session)):
        doc = session.sources.get(document_id)
        if not doc:
            raise HTTPException(404, "Source not found.")
        return doc

    @app.delete("/api/sources/{document_id}")
    async def remove_source(document_id: str, session: Session = Depends(current_session)):
        ensure_idle(session)
        if session.sources.get(document_id) and session.sources[document_id].built_in:
            raise HTTPException(
                400,
                "Built-in demo documents cannot be removed. Disable ENABLE_DEMO_LIBRARY for an empty library.",
            )
        doc = session.sources.pop(document_id, None)
        if not doc:
            raise HTTPException(404, "Source not found.")
        await asyncio.to_thread(session.indexer.delete, doc.content_hash)
        session.verify_cache.clear()
        return {"removed": document_id}

    @app.post("/api/input/upload")
    async def upload_input(file: UploadFile, session: Session = Depends(current_session)):
        data = await read_upload(file)
        try:
            doc = await asyncio.to_thread(parse_document, data, file.filename or "upload", True)
        except DocumentError as exc:
            raise HTTPException(422, str(exc))
        session.inputs.clear()  # Only one active suspicious file is retained.
        session.inputs[doc.document_id] = doc
        return doc

    @app.delete("/api/input")
    async def delete_input(session: Session = Depends(current_session)):
        session.inputs.clear()
        return {"cleared": True}

    @app.post("/api/input/analyze")
    async def analyze_input(body: GenerateRequest, session: Session = Depends(current_session)):
        value = body.text or ""
        if len(value) > config.MAX_TEXT_CHARS:
            raise HTTPException(422, "Text exceeds the character limit.")
        counts = await asyncio.to_thread(segment, value, "Q", "Pasted text")
        return {"word_count": len(words(value)), "sentence_count": len(counts)}

    @app.post("/api/reports/generate", status_code=202)
    async def generate(body: GenerateRequest, session: Session = Depends(current_session)):
        ensure_idle(session)
        if not session.sources:
            raise HTTPException(422, "Upload at least one usable source document.")
        if not body.preview_only and (not session.key or not session.settings.model):
            raise HTTPException(
                422,
                "Configure the selected provider's API key and model, or choose retrieval preview.",
            )
        if bool(body.text and body.text.strip()) == bool(body.input_id):
            raise HTTPException(422, "Provide either pasted text or an uploaded input document.")
        if body.input_id:
            query_doc = session.inputs.get(body.input_id)
            if not query_doc:
                raise HTTPException(404, "Input document not found in this session.")
        else:
            try:
                query_doc = await asyncio.to_thread(
                    parse_document, body.text.encode("utf-8"), "Pasted text.txt", True
                )
            except DocumentError as exc:
                raise HTTPException(422, str(exc))
        ensure_idle(session)  # Parsing yielded; another request may have started a job.
        while len(session.jobs) >= config.MAX_REPORTS:
            del session.jobs[next(iter(session.jobs))]
        job = Job(secrets.token_urlsafe(18))
        session.jobs[job.report_id] = job
        job.emit("Text extracted and segmented", query_sentences=len(query_doc.sentences))
        kwargs = {"client_factory": verifier_client_factory} if verifier_client_factory else {}
        job.task = asyncio.create_task(
            generate_report(
                job,
                session,
                list(session.sources.values()),
                query_doc,
                session.settings.model_copy(deep=True),
                session.key,
                app.state.embeddings,
                body.preview_only,
                **kwargs,
            )
        )
        return {"report_id": job.report_id, "status": job.status}

    def get_job(report_id, session):
        job = session.jobs.get(report_id)
        if not job:
            raise HTTPException(404, "Report not found in this session.")
        return job

    @app.get("/api/reports")
    async def reports(session: Session = Depends(current_session)):
        return {
            "reports": [
                {
                    "report_id": j.report_id,
                    "status": j.status,
                    "created_at": j.result.get("created_at") if j.result else None,
                    "estimated_matched_coverage": (
                        j.result.get("estimated_matched_coverage") if j.result else None
                    ),
                    "query_filename": j.result.get("query_filename") if j.result else None,
                }
                for j in reversed(list(session.jobs.values()))
            ]
        }

    @app.get("/api/reports/{report_id}")
    async def report(report_id: str, session: Session = Depends(current_session)):
        job = get_job(report_id, session)
        return job.result or {"report_id": report_id, "status": job.status}

    @app.post("/api/reports/{report_id}/cancel")
    async def cancel(report_id: str, session: Session = Depends(current_session)):
        job = get_job(report_id, session)
        if job.status in ("queued", "running"):
            job.cancel.set()
            # Cooperative cancellation: an in-flight model encode finishes safely, then stops.
            job.emit("Cancellation requested — waiting for the current operation")
        return {"cancel_requested": job.cancel.is_set()}

    @app.delete("/api/reports/{report_id}")
    async def delete_report(report_id: str, session: Session = Depends(current_session)):
        job = get_job(report_id, session)
        if job.status in ("queued", "running"):
            raise HTTPException(409, "Cancel the active report before deleting it.")
        del session.jobs[report_id]
        return {"removed": report_id}

    @app.get("/api/reports/{report_id}/events")
    async def events(
        report_id: str,
        request: Request,
        after: int = 0,
        session: Session = Depends(current_session),
    ):
        job = get_job(report_id, session)
        try:
            cursor = max(0, int(request.headers.get("last-event-id", after)))
        except ValueError:
            cursor = 0

        async def stream():
            nonlocal cursor
            while True:
                if await request.is_disconnected() or store.get(session.token) is None:
                    return
                for event in job.events[cursor:]:
                    yield f"id: {event['id']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    cursor = event["id"]
                if job.status not in ("queued", "running"):
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.get("/api/reports/{report_id}/download")
    async def download(report_id: str, session: Session = Depends(current_session)):
        job = get_job(report_id, session)
        if not job.result:
            raise HTTPException(409, "The report is still processing.")
        return JSONResponse(
            job.result,
            headers={"Content-Disposition": f'attachment; filename="banglaplag-{report_id}.json"'},
        )

    dist = config.ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        async def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
