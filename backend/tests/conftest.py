from hashlib import sha256
import numpy as np
import pytest
import httpx
from app.bangla_sentence_segmenter import lexical_tokens
from app.main import create_app


class FixtureEmbeddings:
    """Explicit test double. Never selected by application configuration."""

    model_id = "fixture-embedding"
    revision = "v1"

    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(texts)
        vectors = np.zeros((len(texts), 128), np.float32)
        for i, text in enumerate(texts):
            for token in lexical_tokens(text):
                vectors[i, int(sha256(token.encode()).hexdigest()[:8], 16) % 128] += 1
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


@pytest.fixture
def embeddings():
    return FixtureEmbeddings()


@pytest.fixture
def app(embeddings):
    return create_app(embeddings, enable_demo_library=False)


@pytest.fixture
async def client(app):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            await client.post("/api/session")
            yield client
