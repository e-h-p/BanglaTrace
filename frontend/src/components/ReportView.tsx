import { useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  Download,
  FileSearch,
  FileText,
  Info,
  LoaderCircle,
  Printer,
  ShieldCheck,
} from "lucide-react";
import { location, score } from "../api";
import type { Match, Report } from "../types";
import { evidenceRows } from "../reportUtils";
import { downloadReport } from "../reportExport";
import AnnotatedText from "./AnnotatedText";
import ColourLegend from "./ColourLegend";

const statusLabel: Record<string, string> = {
  matched: "Verified match",
  partial: "Needs review",
  unmatched: "No verified match",
  unverified: "Unverified",
};
export default function ReportView({
  report: r,
  back,
}: {
  report: Report;
  back: () => void;
}) {
  const [selected, setSelected] = useState<Match | null>(r.matches[0] ?? null);
  const [filter, setFilter] = useState("all"),
    [source, setSource] = useState(""),
    [sort, setSort] = useState("sentence");
  const [contexts, setContexts] = useState<string[]>([]);
  const [diagnostics, setDiagnostics] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const rows = evidenceRows(r, filter, source, sort);
  const select = (match: Match) => {
    setSelected(match);
    document
      .getElementById("evidence-panel")
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  return (
    <>
      <div className="layout report-layout">
        <article className="sheet" aria-label="Checked document">
          <div className="sheet-head">
            <h1 className="doc-title">{r.query_filename}</h1>
            <div className="sheet-actions no-print">
              <button className="btn ghost" onClick={back}>
                Edit text
              </button>
              <button className="btn ghost" onClick={() => window.print()}>
                <Printer />
                Print / Save PDF
              </button>
              <button
                className="btn primary"
                disabled={downloading}
                title="Download a PDF report with Bengali text, highlights, colour key and source evidence"
                onClick={async () => {
                  setDownloading(true);
                  setDownloadError("");
                  try {
                    await downloadReport(r);
                  } catch {
                    setDownloadError(
                      "Could not prepare the report download. Please try again.",
                    );
                  } finally {
                    setDownloading(false);
                  }
                }}
              >
                {downloading ? <LoaderCircle className="spin" /> : <Download />}
                {downloading ? "Preparing PDF…" : "Download PDF"}
              </button>
              <a
                className="btn ghost"
                href={`/api/reports/${r.report_id}/download`}
                download
                aria-label="Download JSON"
              >
                JSON
              </a>
            </div>
          </div>
          {downloadError && (
            <div role="alert" className="alert error">
              {downloadError}
            </div>
          )}
          <div className="report-meta">
            {new Date(r.created_at).toLocaleString()} ·{" "}
            {r.processing_seconds.toFixed(1)}s processing ·{" "}
            {r.verification_complete
              ? "Verification complete"
              : r.preview_only
                ? "Retrieval preview"
                : "Partial report"}
          </div>
          {!r.verification_complete && (
            <div className="alert warning" role="status">
              <Info size={18} />
              <div>
                <strong>
                  {r.preview_only
                    ? "Retrieval evidence only — semantic verification was not performed."
                    : r.cancelled
                      ? "This report was cancelled before verification finished."
                      : "Verification is incomplete."}
                </strong>
                <p>
                  {r.error ||
                    (r.preview_only
                      ? "Similarity scores are candidate evidence. Configure an AI provider and generate a verified report."
                      : `${r.unverified_candidate_pairs} candidate pairs remain unverified. Any coverage shown includes only confirmed equivalent sentences and may increase after a complete run.`)}
                </p>
              </div>
            </div>
          )}
          <ColourLegend />
          <AnnotatedText
            text={r.query_text}
            matches={r.matches}
            selectedId={selected?.query.sentence_id}
            onSelect={select}
          />
          <div className="annotation-note">
            <Info size={14} />
            <span>
              Input paragraphs and line breaks are preserved. Highlights wrap
              line by line within each sentence; exact copied word spans are not
              inferred.
            </span>
          </div>
        </article>
        <aside className="panel report-sidebar" aria-label="Report findings">
          <section className="card score">
            <div className="score-top">
              <div className="pct">
                {r.preview_only ? "—" : r.estimated_matched_coverage.toFixed(1)}
                {!r.preview_only && <small>%</small>}
              </div>
              <span
                className={`verdict ${r.preview_only || !r.verification_complete ? "mid" : r.matched_sentences ? "high" : "low"}`}
              >
                {r.preview_only
                  ? "Unverified preview"
                  : r.verification_complete
                    ? "Verified coverage"
                    : "Confirmed so far"}
              </span>
            </div>
            <p className="score-sub">
              {r.preview_only
                ? "Retrieval evidence only; semantic verification was not performed."
                : `${r.matched_query_word_count} of ${r.total_eligible_query_word_count} eligible words are in verified equivalent sentences.`}
            </p>
            <div className="map" role="group" aria-label="Document map">
              {r.matches.map((m) => (
                <button
                  key={m.query.sentence_id}
                  className={`map-${m.status} ${selected?.query.sentence_id === m.query.sentence_id ? "sel" : ""}`}
                  style={{ flex: Math.max(1, m.query.word_count) }}
                  aria-label={`Go to sentence ${m.query.sentence_number}: ${statusLabel[m.status]}`}
                  title={`Sentence ${m.query.sentence_number}: ${statusLabel[m.status]}`}
                  onClick={() => select(m)}
                />
              ))}
            </div>
            <div className="map-cap">
              <span>Start</span>
              <span>Each block is one sentence</span>
              <span>End</span>
            </div>
            <p className="coverage-note">
              Sentence-based, word-weighted coverage. Not a probability of
              plagiarism.
            </p>
          </section>
          <section className="card evidence-panel" id="evidence-panel">
            <div className="evidence-heading">
              <FileSearch size={19} />
              <h2>Source evidence</h2>
              {selected && (
                <span className="count-badge">
                  S{selected.query.sentence_number}
                </span>
              )}
            </div>
            {selected ? (
              <>
                <div className="query-evidence">
                  <span className={`pill ${selected.status}`}>
                    {statusLabel[selected.status]}
                  </span>
                  <h4>INPUT SENTENCE {selected.query.sentence_number}</h4>
                  <p lang="bn">{selected.query.original_text}</p>
                </div>
                {!selected.sources.length ? (
                  <div className="evidence-empty">
                    <FileSearch size={28} />
                    <p>
                      {selected.status === "unverified"
                        ? "Retrieval was not completed for this sentence."
                        : "No candidate passed the current retrieval settings."}
                    </p>
                  </div>
                ) : (
                  <div className="evidence-sources">
                    {selected.sources.map((c) => (
                      <article
                        key={c.source.sentence_id}
                        className="evidence-source"
                      >
                        <div className="evidence-source-title">
                          <FileText size={16} />
                          <strong>{c.source.filename}</strong>
                        </div>
                        <small>
                          Sentence {c.source.sentence_number} ·{" "}
                          {location(c.source)}
                        </small>
                        <p lang="bn">{c.source.original_text}</p>
                        <div className="score-pair">
                          <span>
                            LaBSE cosine{" "}
                            <strong>{score(c.cosine_similarity)}</strong>
                          </span>
                          <span>
                            LCS <strong>{score(c.lcs_similarity)}</strong>
                          </span>
                        </div>
                        <span
                          className={`verdict ${c.verification.relation ?? "unverified"}`}
                        >
                          {c.verification.status === "verified"
                            ? c.verification.relation
                            : c.verification.status}
                        </span>
                        <p className="verification-reason">
                          {c.verification.reason}
                        </p>
                        <small>
                          Dense rank {c.dense_rank ?? "—"} · Lexical rank{" "}
                          {c.lexical_rank ?? "—"} · RRF rank {c.fused_rank}
                        </small>
                        <button
                          className="text-button context-toggle"
                          onClick={() =>
                            setContexts((s) =>
                              s.includes(c.source.sentence_id)
                                ? s.filter((id) => id !== c.source.sentence_id)
                                : [...s, c.source.sentence_id],
                            )
                          }
                        >
                          {contexts.includes(c.source.sentence_id)
                            ? "Hide source context"
                            : "View Source Context"}
                          <ChevronDown size={13} />
                        </button>
                        {contexts.includes(c.source.sentence_id) && (
                          <div className="source-context">
                            {r.source_documents
                              .find(
                                (d) => d.document_id === c.source.document_id,
                              )
                              ?.sentences.filter(
                                (s) =>
                                  Math.abs(
                                    s.sentence_number -
                                      c.source.sentence_number,
                                  ) <= 1,
                              )
                              .map((s) => (
                                <p
                                  key={s.sentence_id}
                                  className={
                                    s.sentence_id === c.source.sentence_id
                                      ? "current"
                                      : ""
                                  }
                                  lang="bn"
                                >
                                  <small>S{s.sentence_number}</small>
                                  {s.original_text}
                                </p>
                              ))}
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="empty-small">
                Select an input sentence to view evidence.
              </p>
            )}
          </section>
          <section className="card">
            <h3>What was found</h3>
            <ul className="kinds">
              {(
                [
                  ["matched", "Verified matches", r.matched_sentences],
                  ["partial", "Needs review", r.partial_sentences],
                  ["unmatched", "No verified match", r.unmatched_sentences],
                  ["unverified", "Unverified", r.unverified_sentences],
                ] as const
              ).map(([status, label, count]) => (
                <li key={status}>
                  <button
                    aria-pressed={filter === status}
                    onClick={() =>
                      setFilter(filter === status ? "all" : status)
                    }
                  >
                    <i className={`sw sw-${status}`} />
                    <span>{label}</span>
                    <span className="n">{count}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section className="card">
            <h3>Sources</h3>
            <p className="empty-note">
              {r.matching_source_documents} sources contain confirmed equivalent
              sentences. {r.total_source_documents} sources checked.
            </p>
            <ul className="report-source-list">
              {r.source_documents.map((d) => (
                <li key={d.document_id}>
                  <span lang="bn">{d.filename}</span>
                  <span className="lib-meta">{d.sentence_count} sentences</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
      <div className="report-extras">
        <section className="card matching-panel">
          <div className="section-header">
            <div className="title-icon">
              <FileText size={20} />
            </div>
            <div className="section-heading">
              <h2>Detailed matching table</h2>
              <p>
                Inspect all shortlisted pairs, including rejected and unverified
                candidates.
              </p>
            </div>
            <span className="count-badge">{rows.length} pairs / rows</span>
          </div>
          <div className="table-filters no-print">
            <label>
              Result
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">All sentences</option>
                <option value="matched">Verified matches</option>
                <option value="partial">Partial / needs review</option>
                <option value="unmatched">Unmatched</option>
                <option value="unverified">Unverified</option>
              </select>
            </label>
            <label>
              Source
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="">All source documents</option>
                {r.source_documents.map((d) => (
                  <option key={d.document_id} value={d.document_id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Sort by
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="sentence">Input sentence</option>
                <option value="cosine">LaBSE cosine · highest</option>
                <option value="lcs">LCS · highest</option>
                <option value="source">Source filename</option>
              </select>
            </label>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Input</th>
                  <th>Suspicious sentence</th>
                  <th>Source / location</th>
                  <th title="Cosine is retrieval similarity, not a plagiarism probability">
                    LaBSE
                  </th>
                  <th>LCS</th>
                  <th>Verification</th>
                  <th className="no-print">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ match: m, candidate: c }) => (
                  <tr
                    key={`${m.query.sentence_id}-${c?.source.sentence_id ?? "none"}`}
                  >
                    <td>
                      <span className="table-sentence-id">
                        {String(m.query.sentence_number).padStart(2, "0")}
                      </span>
                    </td>
                    <td className="table-query" lang="bn">
                      {m.query.original_text}
                    </td>
                    <td>
                      {c ? (
                        <>
                          <strong>{c.source.filename}</strong>
                          <small>
                            S{c.source.sentence_number} · {location(c.source)}
                          </small>
                        </>
                      ) : (
                        <span className="muted">No candidate</span>
                      )}
                    </td>
                    <td>{score(c?.cosine_similarity ?? null)}</td>
                    <td>{score(c?.lcs_similarity ?? null)}</td>
                    <td>
                      <span
                        className={`verdict ${c?.verification.relation ?? "unverified"}`}
                      >
                        {c
                          ? c.verification.status === "verified"
                            ? c.verification.relation
                            : c.verification.status
                          : statusLabel[m.status]}
                      </span>
                    </td>
                    <td className="no-print">
                      <button
                        className="icon-button"
                        aria-label={`View evidence for sentence ${m.query.sentence_number}`}
                        onClick={() => select(m)}
                      >
                        <ArrowRight size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && (
              <p className="empty-small">No evidence matches these filters.</p>
            )}
          </div>
        </section>
        <section className="card research-panel">
          <button
            className="research-toggle"
            aria-expanded={diagnostics}
            onClick={() => setDiagnostics(!diagnostics)}
          >
            <span>
              <ShieldCheck size={17} />
              Reproducibility & pipeline diagnostics
            </span>
            <ChevronDown size={17} />
          </button>
          {diagnostics && (
            <div className="research-content">
              <div className="diagnostic-grid">
                <div>
                  <span>AI provider</span>
                  <strong>
                    {r.metadata.verification_configuration.provider ||
                      "openrouter"}
                  </strong>
                </div>
                <div>
                  <span>Retrieval mode</span>
                  <strong>{r.metadata.verification_configuration.mode}</strong>
                </div>
                <div>
                  <span>Requested model</span>
                  <strong>
                    {r.metadata.verification_configuration.model ||
                      "Not configured"}
                  </strong>
                </div>
                <div>
                  <span>Returned models</span>
                  <strong>
                    {r.metadata.actual_models.join(", ") ||
                      "No completed calls"}
                  </strong>
                </div>
                <div>
                  <span>Embedding model</span>
                  <strong>
                    {r.metadata.embedding_model || "Lexical-only"}
                  </strong>
                </div>
                {Object.entries(r.metadata.diagnostics).map(([k, v]) => (
                  <div key={k}>
                    <span>{k.replaceAll("_", " ")}</span>
                    <strong>{v}</strong>
                  </div>
                ))}
              </div>
              <div className="diagnostic-grid">
                {Object.entries(r.metadata.stage_seconds).map(([k, v]) => (
                  <div key={k}>
                    <span>{k}</span>
                    <strong>{v.toFixed(3)}s</strong>
                  </div>
                ))}
                {Object.entries(r.metadata.usage).map(([k, v]) => (
                  <div key={k}>
                    <span>Provider-reported {k.replaceAll("_", " ")}</span>
                    <strong>{v}</strong>
                  </div>
                ))}
              </div>
              <p>{r.metadata.coverage_method}</p>
              <p className="tiny muted">
                No ground-truth accuracy metrics are calculated for user
                uploads. All retrieval settings and the actual verification
                prompt are included in the JSON export.
              </p>
            </div>
          )}
        </section>
        <p className="report-disclaimer">
          <ShieldCheck size={16} />
          {r.metadata.disclaimer} {r.matching_source_documents} source documents
          contain confirmed equivalent sentences.
        </p>
      </div>
    </>
  );
}
