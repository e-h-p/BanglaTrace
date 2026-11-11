import { location, score } from "./api";
import { evidenceRows, textParts } from "./reportUtils";
import { reportHighlightCss, reportHighlights } from "./reportPresentation";
import type { Report } from "./types";

const escapeHtml = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );

export function reportHtml(report: Report, fontCss = "") {
  const e = escapeHtml;
  const text = textParts(report.query_text, report.matches)
    .map((part) =>
      part.match
        ? `<span class="sentence ${part.match.status}" title="${e(reportHighlights[part.match.status].label)}">${e(part.text)}</span>`
        : e(part.text),
    )
    .join("");
  const legend = Object.entries(reportHighlights)
    .map(
      ([status, item]) =>
        `<li><span class="highlight-swatch ${status}"></span><span><b>${item.colour}</b> — ${e(item.label)}</span></li>`,
    )
    .join("");
  const rows = evidenceRows(report, "all", "", "sentence")
    .map(
      ({ match, candidate }) =>
        `<tr><td>S${match.query.sentence_number}<br>${e(reportHighlights[match.status].label)}</td><td class="bn">${e(match.query.original_text)}</td><td>${candidate ? `<b>${e(candidate.source.filename)}</b><br>${e(location(candidate.source))}<br><span class="bn">${e(candidate.source.original_text)}</span>` : "No candidate"}</td><td>${score(candidate?.cosine_similarity ?? null)} / ${score(candidate?.lcs_similarity ?? null)}</td><td>${candidate ? `${e(candidate.verification.status === "verified" ? candidate.verification.relation : candidate.verification.status)}<br>${e(candidate.verification.reason)}` : e(reportHighlights[match.status].label)}</td></tr>`,
    )
    .join("");
  const coverage = report.preview_only
    ? "Unverified preview"
    : `${report.estimated_matched_coverage.toFixed(1)}% verified coverage`;
  const note = report.preview_only
    ? "Retrieval preview only. Semantic verification was not performed; yellow text is unverified."
    : !report.verification_complete
      ? "Verification is incomplete. Coverage includes only confirmed equivalent sentences."
      : "Only verified equivalent sentences contribute to matched coverage.";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'">
<title>BanglaTrace report — ${e(report.query_filename)}</title><style>
${fontCss}
* { box-sizing:border-box; } body { margin:0; padding:32px 24px; background:#f3f5f9; color:#1a2142; font:14px/1.6 'Segoe UI',sans-serif; }
main { max-width:1100px; margin:auto; } header { padding-bottom:18px; } h1 { font-size:24px; margin:6px 0; overflow-wrap:anywhere; } h2 { font-size:17px; margin:0 0 10px; }
.brand { font-size:15px; font-weight:700; color:#2340b8; } .meta,.note { font-size:12px; color:#4b5374; }
.summary,.paper,.evidence { background:#fff; border:1px solid #dce1ec; border-radius:8px; margin:0 0 20px; padding:20px; }
.summary strong { font-size:26px; } .summary p { margin:8px 0 0; }
.colour-legend { border-bottom:1px solid #dce1ec; padding-bottom:16px; margin-bottom:16px; } .colour-legend h2 { font-size:13px; }
.colour-legend ul { display:flex; flex-wrap:wrap; gap:10px 20px; padding:0; margin:0; list-style:none; } .colour-legend li { display:flex; gap:7px; align-items:center; font-size:12px; }
.annotated-text { padding:12px 16px; font:18px/2.05 ReportBengali,'Nirmala UI',serif; }
${reportHighlightCss}
.evidence { padding:20px 12px; } table { width:100%; border-collapse:collapse; table-layout:fixed; font-size:11px; } th,td { border-bottom:1px solid #dce1ec; padding:10px 8px; vertical-align:top; text-align:left; overflow-wrap:anywhere; } th { background:#f3f5f9; } th:first-child { width:100px; } th:nth-child(4) { width:90px; }
.bn { font:13px/1.9 ReportBengali,'Nirmala UI',serif; white-space:pre-wrap; } footer { font-size:12px; color:#4b5374; }
@media(max-width:640px) { body { padding:16px 10px; } .paper { padding:16px; } .annotated-text { padding:10px 0; font-size:17px; } .evidence { overflow:auto; } table { min-width:760px; } }
@media print { @page { margin:16mm; } body { padding:0; background:#fff; } main { max-width:none; } .paper,.summary,.evidence { border:0; border-radius:0; padding:12px 0; } .evidence { overflow:visible; } table { min-width:0; } thead { display:table-header-group; } tr { break-inside:avoid; } .sentence,.highlight-swatch { print-color-adjust:exact; -webkit-print-color-adjust:exact; } }
</style></head><body><main>
<header><div class="brand">BanglaTrace · Sentence-level evidence report</div><h1>${e(report.query_filename)}</h1><div class="meta">${e(new Date(report.created_at).toLocaleString())} · ${report.processing_seconds.toFixed(1)}s · ${e(report.metadata.verification_configuration.provider || "openrouter")} · ${e(report.metadata.verification_configuration.model || "No model configured")}</div></header>
<section class="summary"><strong>${coverage}</strong><p>${e(note)}</p><p>${report.total_sentences} input sentences · ${report.total_source_documents} sources · ${report.matched_sentences} verified matches · ${report.partial_sentences} partial · ${report.unverified_sentences} unverified</p><p class="note">${e(report.metadata.coverage_method)} This is not a probability of plagiarism.</p>${report.error ? `<p>${e(report.error)}</p>` : ""}</section>
<section class="paper"><div class="colour-legend"><h2>Highlight colour key</h2><ul>${legend}</ul></div><div class="annotated-text" lang="bn">${text}</div><p class="note">Input paragraphs, line breaks and spacing are preserved. Highlights cover whole sentences and wrap with the text; they do not identify exact copied word spans.</p></section>
<section class="evidence"><h2>Source evidence — all candidate pairs</h2><table><thead><tr><th>Input / result</th><th>Input sentence</th><th>Source / location / text</th><th>LaBSE / LCS</th><th>Verification / reason</th></tr></thead><tbody>${rows}</tbody></table></section>
<footer>${e(report.metadata.disclaimer)} Report ID: ${e(report.report_id)}. Use your browser’s Print / Save PDF to create a PDF copy. The JSON export contains the complete reproducibility data.</footer>
</main></body></html>`;
}

export async function downloadReport(report: Report) {
  const { renderReportPdf } = await import("./reportPdf");
  const bytes = await renderReportPdf(report);
  if (String.fromCharCode(...bytes.subarray(0, 5)) !== "%PDF-")
    throw new Error("Invalid PDF output");
  const url = URL.createObjectURL(
    new Blob([bytes], { type: "application/pdf" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `banglatrace-report-${report.report_id.replace(/[^\w-]/g, "").slice(0, 48) || "report"}.pdf`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
