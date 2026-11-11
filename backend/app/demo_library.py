"""Bundled, public demo documents; private uploads still belong to their session."""

from . import config
from .document_parser import parse_document


def load_demo_documents():
    documents = []
    for path in sorted(config.DEMO_LIBRARY.glob("*.txt")):
        document = parse_document(path.read_bytes(), path.name)
        document.built_in = True
        documents.append(document)
    if len(documents) > config.MAX_SOURCES:
        raise ValueError("The demo library exceeds MAX_SOURCES. Raise the limit or disable it.")
    if sum(len(d.sentences) for d in documents) > config.MAX_SOURCE_SENTENCES:
        raise ValueError("The demo library exceeds MAX_SOURCE_SENTENCES.")
    if sum(d.size_bytes for d in documents) > config.MAX_SESSION_BYTES:
        raise ValueError("The demo library exceeds MAX_SESSION_MB.")
    return documents
