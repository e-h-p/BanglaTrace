import asyncio
import secrets
import time
from dataclasses import dataclass, field
from . import config
from .schemas import Document, Settings
from .source_indexer import SourceIndexer


@dataclass
class Job:
    report_id: str
    status: str = "queued"
    events: list[dict] = field(default_factory=list)
    result: dict | None = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    def emit(self, stage: str, **details):
        self.events.append(
            {"id": len(self.events) + 1, "stage": stage, "time": time.time(), **details}
        )


@dataclass
class Session:
    token: str
    expires: float
    sources: dict[str, Document] = field(default_factory=dict)
    inputs: dict[str, Document] = field(default_factory=dict)
    settings: Settings = field(
        default_factory=lambda: Settings(
            provider=config.DEFAULT_PROVIDER,
            model=config.ENV_MODELS.get(config.DEFAULT_PROVIDER, ""),
        )
    )
    api_keys: dict[str, str] = field(default_factory=dict, repr=False)
    disabled_env_keys: set[str] = field(default_factory=set)
    provider_models: dict[str, str] = field(default_factory=dict)
    indexer: SourceIndexer = field(default_factory=SourceIndexer)
    jobs: dict[str, Job] = field(default_factory=dict)
    request_times: list[float] = field(default_factory=list)
    upload_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    verify_cache: dict = field(default_factory=dict)

    @property
    def key(self):
        return self.key_for(self.settings.provider)

    def key_for(self, provider):
        return self.api_keys.get(provider, "") or (
            config.ENV_KEYS.get(provider, "") if provider not in self.disabled_env_keys else ""
        )

    @property
    def api_key(self):
        return self.api_keys.get(self.settings.provider, "")

    @api_key.setter
    def api_key(self, value):
        if value:
            self.api_keys[self.settings.provider] = value
        else:
            self.api_keys.pop(self.settings.provider, None)

    @property
    def use_env_key(self):
        return self.settings.provider not in self.disabled_env_keys

    @use_env_key.setter
    def use_env_key(self, value):
        if value:
            self.disabled_env_keys.discard(self.settings.provider)
        else:
            self.disabled_env_keys.add(self.settings.provider)

    def dispose(self):
        for job in self.jobs.values():
            job.cancel.set()
            if job.task and not job.task.done():
                job.task.cancel()
        self.api_keys.clear()
        self.disabled_env_keys.update(config.ENV_KEYS)
        self.provider_models.clear()
        self.sources.clear()
        self.inputs.clear()
        self.indexer.cache.clear()
        self.verify_cache.clear()
        self.jobs.clear()


class SessionStore:
    def __init__(self, demo_documents=()):
        self.sessions: dict[str, Session] = {}
        self.demo_documents = demo_documents

    def prune(self):
        for token, session in list(self.sessions.items()):
            if session.expires < time.time():
                session.dispose()
                del self.sessions[token]

    def create(self) -> Session:
        self.prune()
        if len(self.sessions) >= config.MAX_SESSIONS:
            raise ValueError("Server session capacity reached. Try again later.")
        token = secrets.token_urlsafe(48)
        session = Session(token, time.time() + config.SESSION_TTL)
        session.sources = {d.document_id: d.model_copy(deep=True) for d in self.demo_documents}
        self.sessions[token] = session
        return session

    def get(self, token: str | None) -> Session | None:
        self.prune()
        return self.sessions.get(token or "")

    def delete(self, token: str):
        session = self.sessions.pop(token, None)
        if session:
            session.dispose()
