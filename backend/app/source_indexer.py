from dataclasses import dataclass
from threading import Lock
import numpy as np
from rank_bm25 import BM25Plus
from .schemas import Document, Sentence
from .bangla_sentence_segmenter import lexical_tokens, SEGMENTER_VERSION
from .embedding_service import EmbeddingProvider


@dataclass
class SourceIndex:
    sentences: list[Sentence]
    vectors: np.ndarray | None
    lexical: BM25Plus
    token_sets: list[set[str]]


class SourceIndexer:
    """Session-owned content-addressed embedding cache, deleted with its session/documents."""

    def __init__(self):
        self.cache: dict[str, np.ndarray] = {}
        self.lock = Lock()

    def build(
        self, documents: list[Document], provider: EmbeddingProvider, dense=True
    ) -> SourceIndex:
        sentences, matrices = [], []
        with self.lock:
            for doc in documents:
                sentences.extend(doc.sentences)
                if dense:
                    key = f"{doc.content_hash}:{provider.model_id}:{provider.revision}:{SEGMENTER_VERSION}"
                    if key not in self.cache:
                        self.cache[key] = provider.encode(
                            [s.normalized_text for s in doc.sentences]
                        )
                    matrices.append(self.cache[key])
        tokens = [lexical_tokens(s.normalized_text) or ["_"] for s in sentences]
        return SourceIndex(
            sentences,
            np.concatenate(matrices) if matrices else None,
            BM25Plus(tokens),
            [set(t) for t in tokens],
        )

    def delete(self, digest: str):
        with self.lock:
            for key in list(self.cache):
                if key.startswith(digest + ":"):
                    del self.cache[key]
