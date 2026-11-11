"""All runtime artifacts stay inside this experiment, including model downloads."""

import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
RUNTIME = ROOT / ".runtime"
(RUNTIME / "uploads").mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(RUNTIME / "uploads")
os.environ.setdefault("HF_HOME", str(RUNTIME / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(RUNTIME / "torch"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
MODEL = "sentence-transformers/LaBSE"
MODEL_REVISION = os.getenv("LABSE_REVISION", "main")
DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
MAX_SOURCES = int(os.getenv("MAX_SOURCES", "30"))
MAX_SOURCE_SENTENCES = int(os.getenv("MAX_SOURCE_SENTENCES", "12000"))
MAX_QUERY_SENTENCES = int(os.getenv("MAX_QUERY_SENTENCES", "500"))
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "500000"))
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "500"))
MAX_SESSION_BYTES = int(os.getenv("MAX_SESSION_MB", "100")) * 1024 * 1024
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "7200"))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "32"))
MAX_REPORTS = int(os.getenv("MAX_REPORTS", "10"))
MAX_PAIR_CHARS = int(os.getenv("MAX_PAIR_CHARS", "16000"))
SECURE_COOKIE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE = "banglaplag_session"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
).split(",")
ENV_KEY = os.getenv("OPENROUTER_API_KEY", "")
ENV_MODEL = os.getenv("OPENROUTER_MODEL", "")
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
ENV_KEYS = {
    "openrouter": ENV_KEY,
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
}
ENV_MODELS = {
    "openrouter": ENV_MODEL,
    "openai": os.getenv("OPENAI_MODEL", ""),
    "anthropic": os.getenv("ANTHROPIC_MODEL", ""),
}
DEMO_LIBRARY = ROOT / "demo-library"
ENABLE_DEMO_LIBRARY = os.getenv("ENABLE_DEMO_LIBRARY", "true").lower() == "true"
