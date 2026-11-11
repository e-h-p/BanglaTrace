import type { Match, Report, Sentence, Settings } from "../types";

export function reportFixture(): Report {
  const texts = [
    "নদী আমাদের কৃষিকাজে পানি সরবরাহ করে।",
    "মানুষ নদীর আশপাশে বসতি গড়ে তোলে।",
    "এই বাক্যটি এখনো যাচাই করা হয়নি।",
    "আমি নিজের অভিজ্ঞতা নিয়ে লিখছি।",
  ];
  const input = `  🌿 ${texts[0]}  ${texts[1]}\n\n${texts[2]}\n\t${texts[3]}  `;
  const statuses: Match["status"][] = [
    "matched",
    "partial",
    "unverified",
    "unmatched",
  ];
  const sentence = (text: string, i: number): Sentence => {
    const start = Array.from(input.slice(0, input.indexOf(text))).length;
    return {
      document_id: "Q",
      filename: "Demo.txt",
      sentence_id: `Q_S${i + 1}`,
      sentence_number: i + 1,
      original_text: text,
      normalized_text: text,
      char_start: start,
      char_end: start + Array.from(text).length,
      word_count: text.split(/\s+/).length,
      page_number: null,
      page_end: null,
      line_start: i + 1,
      line_end: i + 1,
      location_type: "physical",
    };
  };
  const matches = texts.map((text, i): Match => ({
    query: sentence(text, i),
    status: statuses[i],
    sources: [
      {
        source: {
          ...sentence(text, i),
          document_id: "D",
          sentence_id: `D_S${i + 1}`,
          filename: "Rivers.txt",
        },
        cosine_similarity: 0.9,
        lcs_similarity: 0.7,
        dense_rank: 1,
        lexical_rank: 1,
        fused_rank: 1,
        fused_score: 0.03,
        verification: {
          status: i === 2 ? "unverified" : "verified",
          relation:
            i === 0
              ? "equivalent"
              : i === 1
                ? "partial"
                : i === 2
                  ? null
                  : "unrelated",
          reason: "Fixture evidence.",
          actual_model: "fixture-model",
          attempts: 1,
        },
      },
    ],
  }));
  return {
    report_id: "report-fixture",
    status: "partial",
    preview_only: false,
    cancelled: false,
    error: null,
    created_at: "2026-11-05T12:00:00Z",
    processing_seconds: 0.5,
    estimated_matched_coverage: 25,
    matched_query_word_count: matches[0].query.word_count,
    total_eligible_query_word_count: matches.reduce(
      (n, m) => n + m.query.word_count,
      0,
    ),
    total_sentences: 4,
    matched_sentences: 1,
    partial_sentences: 1,
    unmatched_sentences: 1,
    unverified_sentences: 1,
    matching_source_documents: 1,
    total_source_documents: 1,
    verification_complete: false,
    unverified_candidate_pairs: 1,
    query_text: input,
    query_filename: "Demo.txt",
    matches,
    source_documents: [
      {
        document_id: "D",
        filename: "Rivers.txt",
        file_type: "TXT",
        size_bytes: 100,
        page_count: null,
        sentence_count: 4,
        status: "indexed",
        warnings: [],
        text: texts.join("\n"),
        sentences: matches.map((m) => m.sources[0].source),
      },
    ],
    metadata: {
      pipeline_version: "fixture",
      verification_configuration: {
        provider: "openrouter",
        mode: "lcs",
        model: "fixture-model",
      } as Settings,
      diagnostics: {},
      stage_seconds: {},
      usage: {},
      actual_models: ["fixture-model"],
      coverage_method: "Word-weighted verified coverage.",
      disclaimer: "Evidence for review.",
      embedding_model: null,
      embedding_revision: null,
    },
  };
}
