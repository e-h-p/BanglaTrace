export type Sentence = {
  document_id: string;
  filename: string;
  sentence_id: string;
  sentence_number: number;
  original_text: string;
  normalized_text: string;
  char_start: number;
  char_end: number;
  word_count: number;
  page_number: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  location_type: "physical" | "extracted";
};
export type Source = {
  built_in?: boolean;
  document_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  page_count: number | null;
  sentence_count: number;
  status: string;
  warnings: string[];
};
export type Document = Source & { text: string; sentences: Sentence[] };
export type Provider = "openrouter" | "openai" | "anthropic";
export type Settings = {
  provider: Provider;
  provider_accounts?: Partial<
    Record<
      Provider,
      { model: string; key_configured: boolean; key_source: string | null }
    >
  >;
  model: string;
  prompt: string;
  temperature: number;
  max_tokens: number;
  dense_top_k: number;
  lexical_prefilter_k: number;
  lexical_top_k: number;
  max_candidates: number;
  min_cosine: number | null;
  min_lcs: number | null;
  parallel_requests: number;
  timeout_seconds: number;
  mode: "hybrid" | "dense" | "lcs";
  json_mode: boolean;
  key_configured: boolean;
  key_source: string | null;
  expires_at: number;
};
export type Verdict = {
  status: "verified" | "failed" | "unverified";
  relation:
    | "equivalent"
    | "partial"
    | "contradiction"
    | "unrelated"
    | "uncertain"
    | null;
  reason: string;
  actual_model: string | null;
  attempts: number;
};
export type Candidate = {
  source: Sentence;
  cosine_similarity: number | null;
  lcs_similarity: number;
  dense_rank: number | null;
  lexical_rank: number | null;
  fused_rank: number;
  fused_score: number;
  verification: Verdict;
};
export type Match = {
  query: Sentence;
  sources: Candidate[];
  status: "matched" | "partial" | "unmatched" | "unverified";
};
export type Report = {
  report_id: string;
  status: string;
  preview_only: boolean;
  cancelled: boolean;
  error: string | null;
  created_at: string;
  processing_seconds: number;
  estimated_matched_coverage: number;
  matched_query_word_count: number;
  total_eligible_query_word_count: number;
  total_sentences: number;
  matched_sentences: number;
  partial_sentences: number;
  unmatched_sentences: number;
  unverified_sentences: number;
  matching_source_documents: number;
  total_source_documents: number;
  verification_complete: boolean;
  unverified_candidate_pairs: number;
  query_text: string;
  query_filename: string;
  matches: Match[];
  source_documents: Document[];
  metadata: {
    pipeline_version: string;
    verification_configuration: Settings;
    diagnostics: Record<string, number>;
    stage_seconds: Record<string, number>;
    usage: Record<string, number>;
    actual_models: string[];
    coverage_method: string;
    disclaimer: string;
    embedding_model: string | null;
    embedding_revision: string | null;
  };
};
export type ProgressEvent = {
  id: number;
  stage: string;
  time: number;
  completed?: number;
  total?: number;
  terminal?: boolean;
  status?: string;
  error?: string;
};
export type ReportItem = {
  report_id: string;
  status: string;
  created_at: string | null;
  estimated_matched_coverage: number | null;
  query_filename: string | null;
};
export type SessionInfo = {
  expires_at: number;
  limits: {
    max_upload_mb: number;
    max_sources: number;
    max_query_sentences: number;
    max_source_sentences: number;
  };
  settings: Settings;
};
