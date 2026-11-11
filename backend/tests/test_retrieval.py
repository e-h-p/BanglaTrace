import numpy as np
import pytest
from app.document_parser import parse_document
from app.source_indexer import SourceIndexer
from app.hybrid_ranker import lcs_similarity, dense_retrieve, fuse_candidates, lexical_retrieve
from app.schemas import Settings


def test_cosine_ranking():
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.6]], dtype=np.float32)
    assert [i for i, _ in dense_retrieve(vectors, np.array([1.0, 0.0]), 2)] == [0, 2]


def test_lcs_normalized():
    assert lcs_similarity("বাংলা ভাষা", "বাংলা ভাষা") == 1
    assert lcs_similarity("abc", "axc") == pytest.approx(2 / 3)
    assert lcs_similarity("abc", "xyz") == 0


def test_cache_and_delete(embeddings):
    doc = parse_document("ঢাকা একটি শহর।".encode(), "a.txt")
    indexer = SourceIndexer()
    indexer.build([doc], embeddings)
    indexer.build([doc], embeddings)
    assert len(embeddings.calls) == 1
    indexer.delete(doc.content_hash)
    indexer.build([doc], embeddings)
    assert len(embeddings.calls) == 2


def test_hybrid_multiple_sources_deduplication(embeddings):
    query = "বাংলাদেশের রাজধানী ঢাকা।"
    documents = [
        parse_document((query + " নদী বহমান।").encode(), "a.txt"),
        parse_document((query + " গাছ সবুজ।").encode(), "b.txt"),
    ]
    index = SourceIndexer().build(documents, embeddings)
    candidates, counts = fuse_candidates(
        index, query, embeddings.encode([query])[0], Settings(max_candidates=6)
    )
    exact = [c for c in candidates if c.source.original_text == query]
    assert len(exact) == 2
    assert len({c.source.sentence_id for c in candidates}) == len(candidates)
    assert all(c.dense_rank is not None and c.lexical_rank is not None for c in exact)
    assert counts["fused"] >= len(candidates)


def test_no_bm25_floor_false_candidates(embeddings):
    doc = parse_document("মেঘ বৃষ্টি আনে।".encode(), "a.txt")
    index = SourceIndexer().build([doc], embeddings, False)
    assert lexical_retrieve(index, "পাহাড় সুন্দর", 20, 10) == []


def test_both_branches_preserved_at_candidate_cap(embeddings):
    doc = parse_document("alpha beta. gamma delta. epsilon zeta.".encode(), "a.txt")
    index = SourceIndexer().build([doc], embeddings)
    # Intentionally arrange dense ranks away from the literal branch.
    index.vectors = np.array([[0.0, 1.0], [1.0, 0.0], [0.9, 0.1]], dtype=np.float32)
    candidates, _ = fuse_candidates(
        index, "alpha beta.", np.array([1.0, 0.0]), Settings(max_candidates=2)
    )
    assert {c.source.sentence_number for c in candidates} == {1, 2}


def test_modes_and_optional_filters(embeddings):
    doc = parse_document("ঢাকা রাজধানী। নদী বহমান।".encode(), "a.txt")
    index = SourceIndexer().build([doc], embeddings)
    q = embeddings.encode(["ঢাকা রাজধানী।"])[0]
    for mode in ("lcs", "dense", "hybrid"):
        matches, _ = fuse_candidates(
            index, "ঢাকা রাজধানী।", q, Settings(mode=mode, min_lcs=1, min_cosine=0.9)
        )
        assert matches[0].source.sentence_number == 1
        if mode == "dense":
            assert matches[0].lexical_rank is None
        if mode == "lcs":
            assert matches[0].dense_rank is None
