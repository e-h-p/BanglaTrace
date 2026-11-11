from .schemas import Alignment


def classify(alignment: Alignment) -> str:
    verdicts = [c.verification for c in alignment.sources]
    if any(v.status == "verified" and v.relation == "equivalent" for v in verdicts):
        return "matched"
    if any(v.status != "verified" for v in verdicts):
        return "unverified"
    if any(v.relation == "uncertain" for v in verdicts):
        return "unverified"
    if any(v.relation == "partial" for v in verdicts):
        return "partial"
    return "unmatched"


def calculate_coverage(alignments: list[Alignment]) -> dict:
    counts = {k: 0 for k in ("matched", "partial", "unmatched", "unverified")}
    matched_words, total_words, sources = 0, 0, set()
    for row in alignments:
        row.status = classify(row)
        counts[row.status] += 1
        total_words += row.query.word_count
        if row.status == "matched":
            matched_words += row.query.word_count
            sources.update(
                c.source.document_id
                for c in row.sources
                if c.verification.status == "verified" and c.verification.relation == "equivalent"
            )
    return {
        "estimated_matched_coverage": (
            round(100 * matched_words / total_words, 2) if total_words else 0
        ),
        "matched_query_word_count": matched_words,
        "total_eligible_query_word_count": total_words,
        "total_sentences": len(alignments),
        "matching_source_documents": len(sources),
        **{k + "_sentences": v for k, v in counts.items()},
    }
