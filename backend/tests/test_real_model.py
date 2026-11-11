import os
import numpy as np
import pytest


@pytest.mark.model
@pytest.mark.skipif(
    os.getenv("RUN_MODEL_TESTS") != "1",
    reason="Opt-in LaBSE download/inference; set RUN_MODEL_TESTS=1.",
)
def test_real_labse_bangla_ranking():
    from app.embedding_service import LaBSEEmbeddings
    from app.hybrid_ranker import dense_retrieve

    provider = LaBSEEmbeddings()
    texts = ["বাংলাদেশের রাজধানী ঢাকা।", "ঢাকা বাংলাদেশের রাজধানী।", "রান্নার জন্য আলু কাটা হয়েছে।"]
    vectors = provider.encode(texts)
    assert vectors.shape == (3, 768)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    ranking = dense_retrieve(vectors, vectors[0], 3)
    assert [i for i, _ in ranking] == [0, 1, 2]
    assert ranking[0][1] > 0.99
