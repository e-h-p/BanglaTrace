from threading import Lock
from typing import Protocol
import numpy as np
from . import config


class EmbeddingProvider(Protocol):
    model_id: str
    revision: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class LaBSEEmbeddings:
    model_id = config.MODEL
    revision = config.MODEL_REVISION

    def __init__(self):
        self._model = None
        self._lock = Lock()
        self.resolved_revision = None

    def encode(self, texts: list[str]) -> np.ndarray:
        # One model and one bounded CPU/GPU inference operation per process.
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self.model_id,
                    device=config.DEVICE,
                    revision=self.revision,
                    cache_folder=str(config.RUNTIME / "models"),
                )
                self.resolved_revision = getattr(
                    self._model[0].auto_model.config, "_commit_hash", None
                )
            if not texts:
                return np.empty(
                    (0, self._model.get_sentence_embedding_dimension()), dtype=np.float32
                )
            # Never silently truncate a long sentence: mean-pool all tokenizer chunks.
            tokenizer = self._model.tokenizer
            chunks, owners = [], []
            window = self._model.max_seq_length - tokenizer.num_special_tokens_to_add(pair=False)
            for index, text in enumerate(texts):
                ids = tokenizer.encode(text, add_special_tokens=False)
                if len(ids) <= window:
                    chunks.append(text)
                    owners.append(index)
                    continue
                for start in range(0, max(1, len(ids)), window):
                    chunks.append(
                        tokenizer.decode(ids[start : start + window], skip_special_tokens=True)
                    )
                    owners.append(index)
            values = self._model.encode(
                chunks,
                batch_size=16,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            vectors = np.zeros((len(texts), values.shape[1]), dtype=np.float32)
            np.add.at(vectors, owners, values)
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            return vectors / np.maximum(norms, 1e-12)
