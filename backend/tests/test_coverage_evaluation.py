import pytest
from app.schemas import Alignment, Candidate, Verification
from app.bangla_sentence_segmenter import segment
from app.coverage_calculator import calculate_coverage
from app.evaluation import retrieval_metrics, alignment_metrics, latency_metrics


def test_word_weighting_duplicate_source_and_contradiction():
    q = segment("ঢাকা বাংলাদেশের রাজধানী। মানুষ নদীতে মাছ ধরে।", "Q", "q.txt")
    src = segment("ঢাকা বাংলাদেশের রাজধানী।", "D", "s.txt")[0]
    positive = Candidate(
        source=src,
        lcs_similarity=1,
        verification=Verification(
            status="verified", relation="equivalent", reason="Same proposition."
        ),
    )
    negative = positive.model_copy(deep=True)
    negative.verification.relation = "contradiction"
    rows = [
        Alignment(query=q[0], sources=[positive, positive]),
        Alignment(query=q[1], sources=[negative]),
    ]
    summary = calculate_coverage(rows)
    assert summary["matched_query_word_count"] == 3
    assert summary["total_eligible_query_word_count"] == 7
    assert summary["estimated_matched_coverage"] == 42.86
    assert summary["matching_source_documents"] == 1
    assert summary["matched_sentences"] == 1 and summary["unmatched_sentences"] == 1


@pytest.mark.parametrize(
    "status,relation,expected",
    [
        ("verified", "partial", "partial"),
        ("failed", None, "unverified"),
        ("verified", "uncertain", "unverified"),
        ("verified", "contradiction", "unmatched"),
        ("verified", "unrelated", "unmatched"),
    ],
)
def test_non_equivalent_does_not_count(status, relation, expected):
    q = segment("বাংলা লেখা।", "Q", "q.txt")[0]
    row = Alignment(
        query=q,
        sources=[
            Candidate(
                source=q,
                lcs_similarity=1,
                verification=Verification(status=status, relation=relation, reason="Fixture."),
            )
        ],
    )
    result = calculate_coverage([row])
    assert result["estimated_matched_coverage"] == 0 and row.status == expected


def test_empty_coverage():
    assert calculate_coverage([])["estimated_matched_coverage"] == 0


def test_evaluation_requires_truth_and_measured_values():
    with pytest.raises(ValueError):
        retrieval_metrics({}, {})
    result = retrieval_metrics({"Q": ["A", "C", "B"]}, {"Q": {"B", "A"}}, 2)
    assert (
        result["recall_at_k"] == 0.5 and result["precision_at_k"] == 0.5 and result["mrr_at_k"] == 1
    )
    result = alignment_metrics(
        {("Q", "A"), ("Q", "C")},
        {("Q", "A"), ("Q", "B")},
        {("Q", "A"), ("Q", "B"), ("Q", "C"), ("Q", "D")},
    )
    assert result == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "false_positive_rate": 0.5}
    assert latency_metrics([1, 2, 3])["mean_seconds"] == 2
