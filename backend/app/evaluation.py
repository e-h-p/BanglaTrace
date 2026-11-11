"""Evaluation requires explicit human ground truth; never infer it from model labels."""


def retrieval_metrics(rankings: dict[str, list[str]], relevant: dict[str, set[str]], k=10):
    if k < 1:
        raise ValueError("k must be positive")
    if not relevant:
        raise ValueError("Ground-truth relevance annotations are required.")
    recalls, precisions, rr = [], [], []
    for query, truth in relevant.items():
        if not truth:
            continue
        ranked = list(dict.fromkeys(rankings.get(query, [])))[:k]
        hits = len(set(ranked) & truth)
        recalls.append(hits / len(truth))
        precisions.append(hits / k)
        rr.append(next((1 / (i + 1) for i, sid in enumerate(ranked) if sid in truth), 0))
    if not recalls:
        raise ValueError("At least one query must have a relevant source.")
    return {
        "recall_at_k": sum(recalls) / len(recalls),
        "precision_at_k": sum(precisions) / len(precisions),
        "mrr_at_k": sum(rr) / len(rr),
        "k": k,
        "evaluated_queries": len(recalls),
    }


def alignment_metrics(
    predicted: set[tuple[str, str]],
    gold: set[tuple[str, str]],
    universe: set[tuple[str, str]] | None = None,
):
    if gold is None:
        raise ValueError("Ground truth is required.")
    tp, fp, fn = len(predicted & gold), len(predicted - gold), len(gold - predicted)
    precision, recall = tp / (tp + fp) if tp + fp else 0, tp / (tp + fn) if tp + fn else 0
    output = {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
    }
    if universe is not None:
        if not (predicted | gold) <= universe:
            raise ValueError("Universe must include all annotated and predicted pairs.")
        negatives = len(universe - gold)
        output["false_positive_rate"] = fp / negatives if negatives else None
    return output


def latency_metrics(seconds: list[float]):
    import numpy as np

    if not seconds or any(v < 0 for v in seconds):
        raise ValueError("Supply nonnegative measured latencies.")
    return {
        "mean_seconds": float(np.mean(seconds)),
        "p50_seconds": float(np.percentile(seconds, 50)),
        "p95_seconds": float(np.percentile(seconds, 95)),
        "samples": len(seconds),
    }
