import numpy as np
from rapidfuzz.distance import LCSseq
from .bangla_sentence_segmenter import lexical_tokens
from .schemas import Candidate, Settings
from .source_indexer import SourceIndex


def lcs_similarity(a: str, b: str) -> float:
    """Character LCS length / max character length, after NFC/whitespace normalization upstream."""
    return float(LCSseq.normalized_similarity(a, b))


def dense_retrieve(vectors: np.ndarray, query: np.ndarray, top_k: int):
    scores = np.clip(vectors @ query, -1, 1)
    order = np.argsort(-scores, kind="stable")[:top_k]
    return [(int(i), float(scores[i])) for i in order]


def lexical_retrieve(index: SourceIndex, text: str, prefilter_k: int, top_k: int):
    tokens = lexical_tokens(text)
    scores = index.lexical.get_scores(tokens)
    # BM25Plus has a corpus-wide delta floor; require actual token intersection.
    overlap = np.array([bool(set(tokens) & t) for t in index.token_sets])
    valid = np.flatnonzero(overlap)
    shortlist = valid[np.argsort(-scores[valid], kind="stable")[:prefilter_k]]
    reranked = [
        (int(i), lcs_similarity(text, index.sentences[i].normalized_text)) for i in shortlist
    ]
    return sorted(reranked, key=lambda pair: (-pair[1], pair[0]))[:top_k]


def fuse_candidates(index: SourceIndex, text: str, query: np.ndarray | None, settings: Settings):
    dense = (
        dense_retrieve(index.vectors, query, settings.dense_top_k) if settings.mode != "lcs" else []
    )
    lexical = (
        lexical_retrieve(index, text, settings.lexical_prefilter_k, settings.lexical_top_k)
        if settings.mode != "dense"
        else []
    )
    return fuse_rankings(index, text, query, settings, dense, lexical)


def fuse_rankings(
    index: SourceIndex, text: str, query: np.ndarray | None, settings: Settings, dense, lexical
):
    if settings.min_cosine is not None:
        dense = [(i, s) for i, s in dense if s >= settings.min_cosine]
    if settings.min_lcs is not None:
        lexical = [(i, s) for i, s in lexical if s >= settings.min_lcs]
    merged = {}
    for branch, ranking in [("dense", dense), ("lexical", lexical)]:
        for rank, (i, _) in enumerate(ranking, 1):
            if i not in merged:
                merged[i] = Candidate(
                    source=index.sentences[i],
                    cosine_similarity=(
                        float(np.clip(index.vectors[i] @ query, -1, 1))
                        if index.vectors is not None and query is not None
                        else None
                    ),
                    lcs_similarity=lcs_similarity(text, index.sentences[i].normalized_text),
                )
            candidate = merged[i]
            if branch == "dense":
                candidate.dense_rank = rank
            else:
                candidate.lexical_rank = rank
            candidate.fused_score += 1 / (60 + rank)
    ordered = sorted(merged, key=lambda i: (-merged[i].fused_score, index.sentences[i].sentence_id))
    for rank, i in enumerate(ordered, 1):
        merged[i].fused_rank = rank
    # Reserve the best available candidate from each branch, then fill by RRF.
    reserved = list(
        dict.fromkeys(([dense[0][0]] if dense else []) + ([lexical[0][0]] if lexical else []))
    )
    selected = list(dict.fromkeys(reserved + ordered))[: settings.max_candidates]
    selected.sort(key=lambda i: merged[i].fused_rank)
    return [merged[i] for i in selected], dict(
        dense=len(dense), lexical=len(lexical), fused=len(merged), selected=len(selected)
    )
