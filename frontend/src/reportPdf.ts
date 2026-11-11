import type {
  Content,
  ContentText,
  TDocumentDefinitions,
} from "pdfmake/interfaces";
import { location, score } from "./api";
import { textParts } from "./reportUtils";
import { reportHighlights } from "./reportPresentation";
import type { Match, Report } from "./types";

const backgrounds: Partial<Record<Match["status"], string>> = {
  matched: "#fde8e8",
  partial: "#ffeddf",
  unverified: "#fff4bd",
};

export function reportPdfDefinition(report: Report): TDocumentDefinitions {
  const coverage = report.preview_only
    ? "Unverified preview"
    : `${report.estimated_matched_coverage.toFixed(1)}% verified coverage`;
  const note = report.preview_only
    ? "Retrieval preview only. Semantic verification was not performed; yellow text is unverified."
    : !report.verification_complete
      ? "Verification is incomplete. Coverage includes only confirmed equivalent sentences."
      : "Only verified equivalent sentences contribute to matched coverage.";
  const input: ContentText[] = textParts(report.query_text, report.matches).map(
    (part) => ({
      text: part.text,
      ...(part.match && backgrounds[part.match.status]
        ? { background: backgrounds[part.match.status] }
        : {}),
      preserveLeadingSpaces: true,
      preserveTrailingSpaces: true,
    }),
  );
  const evidence: Content[] = [];
  for (const match of report.matches) {
    evidence.push(
      {
        text: `Sentence ${match.query.sentence_number} - ${reportHighlights[match.status].label}`,
        style: "sentenceHeading",
      },
      {
        text: match.query.original_text,
        style: "query",
        preserveLeadingSpaces: true,
        preserveTrailingSpaces: true,
      },
    );
    if (!match.sources.length)
      evidence.push({
        text: "No candidate passed the current retrieval settings.",
        style: "note",
      });
    for (const candidate of match.sources) {
      const verdict =
        candidate.verification.status === "verified"
          ? candidate.verification.relation
          : candidate.verification.status;
      evidence.push({
        table: {
          widths: ["*"],
          body: [
            [
              {
                stack: [
                  { text: candidate.source.filename, bold: true, fontSize: 10 },
                  {
                    text: `Source sentence ${candidate.source.sentence_number} - ${location(candidate.source).replace(/[–—]/g, "-")}`,
                    style: "note",
                  },
                  {
                    text: candidate.source.original_text,
                    fontSize: 11,
                    lineHeight: 1.5,
                    margin: [0, 5, 0, 5],
                  },
                  {
                    text: `Verification: ${verdict ?? "unverified"} | LaBSE cosine: ${score(candidate.cosine_similarity)} | LCS: ${score(candidate.lcs_similarity)}`,
                    style: "note",
                  },
                  {
                    text: candidate.verification.reason,
                    fontSize: 9,
                    lineHeight: 1.4,
                    margin: [0, 4, 0, 0],
                  },
                ],
                margin: [8, 6, 8, 6],
              },
            ],
          ],
        },
        layout: {
          hLineWidth: () => 0.5,
          vLineWidth: () => 0.5,
          hLineColor: () => "#e1e4ec",
          vLineColor: () => "#e1e4ec",
        },
        margin: [0, 0, 0, 9],
      });
    }
  }
  return {
    pageSize: "A4",
    pageMargins: [44, 40, 44, 42],
    info: {
      title: `BanglaTrace report - ${report.query_filename}`,
      author: "BanglaTrace",
      subject: "Sentence-level source evidence",
    },
    defaultStyle: {
      font: "ReportBengali",
      fontSize: 10,
      color: "#1a2142",
      lineHeight: 1.35,
    },
    footer: (page, pages) => ({
      text: `BanglaTrace | Page ${page} of ${pages}`,
      alignment: "center",
      fontSize: 8,
      color: "#667085",
      margin: [44, 12, 44, 0],
    }),
    styles: {
      title: { fontSize: 19, bold: true, margin: [0, 5, 0, 6] },
      heading: { fontSize: 13, bold: true, margin: [0, 14, 0, 8] },
      note: {
        fontSize: 8.5,
        color: "#4b5374",
        lineHeight: 1.4,
        margin: [0, 3, 0, 4],
      },
      sentenceHeading: { fontSize: 11, bold: true, margin: [0, 14, 0, 5] },
      query: { fontSize: 11.5, lineHeight: 1.5, margin: [0, 0, 0, 8] },
    },
    content: [
      {
        text: "BanglaTrace - Sentence-level evidence report",
        color: "#2340b8",
        fontSize: 10,
        bold: true,
      },
      { text: report.query_filename, style: "title" },
      {
        text: `${new Date(report.created_at).toLocaleString()} | ${report.processing_seconds.toFixed(1)}s | ${report.metadata.verification_configuration.provider || "openrouter"} | ${report.metadata.verification_configuration.model || "No model configured"}`,
        style: "note",
      },
      { text: coverage, fontSize: 17, bold: true, margin: [0, 13, 0, 4] },
      { text: note, style: "note" },
      {
        text: `${report.total_sentences} input sentences | ${report.total_source_documents} sources | ${report.matched_sentences} verified matches | ${report.partial_sentences} partial | ${report.unverified_sentences} unverified`,
        style: "note",
      },
      {
        text: `${report.metadata.coverage_method} This is not a probability of plagiarism.`,
        style: "note",
      },
      ...(report.error ? [{ text: report.error, style: "note" }] : []),
      { text: "Highlight colour key", style: "heading" },
      {
        text: [
          {
            text: "Red",
            bold: true,
            color: "#c92a35",
            background: backgrounds.matched,
          },
          { text: " - Verified match\n" },
          {
            text: "Orange",
            bold: true,
            color: "#b94d09",
            background: backgrounds.partial,
          },
          { text: " - Partial / needs review\n" },
          {
            text: "Yellow",
            bold: true,
            color: "#997400",
            background: backgrounds.unverified,
          },
          { text: " - Unverified\n" },
          { text: "None", bold: true },
          { text: " - No verified match" },
        ],
        fontSize: 9,
        lineHeight: 1.5,
        margin: [0, 0, 0, 12],
      },
      {
        text: input,
        fontSize: 12,
        lineHeight: 1.65,
        preserveLeadingSpaces: true,
        preserveTrailingSpaces: true,
        margin: [0, 0, 0, 12],
      },
      {
        text: "Input paragraphs and line breaks are preserved. Highlights cover complete sentences; exact copied word spans are not inferred.",
        style: "note",
      },
      {
        text: "Source evidence - all candidate pairs",
        style: "heading",
        pageBreak: "before",
      },
      ...evidence,
      {
        text: `${report.metadata.disclaimer} Report ID: ${report.report_id}. The JSON export contains complete reproducibility data.`,
        style: "note",
        margin: [0, 15, 0, 0],
      },
    ],
  };
}

let fontsPromise: Promise<Record<string, string>> | undefined;
async function loadFonts() {
  if (!fontsPromise)
    fontsPromise = Promise.all(
      ["Regular", "SemiBold"].map(async (weight) => {
        const name = `NotoSerifBengali-${weight}.ttf`;
        const response = await fetch(`/assets/moulik/fonts/${name}`, {
          credentials: "same-origin",
          signal: AbortSignal.timeout(15000),
        });
        if (!response.ok)
          throw new Error("Could not load the bundled PDF font.");
        const bytes = new Uint8Array(await response.arrayBuffer());
        let binary = "";
        for (let i = 0; i < bytes.length; i += 8192)
          binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        return [name, btoa(binary)] as const;
      }),
    )
      .then((entries) => Object.fromEntries(entries))
      .catch((error) => {
        fontsPromise = undefined;
        throw error;
      });
  return fontsPromise;
}

export async function renderReportPdf(
  report: Report,
): Promise<Uint8Array<ArrayBuffer>> {
  const [{ default: pdfMake }, fonts] = await Promise.all([
    import("pdfmake/build/pdfmake"),
    loadFonts(),
  ]);
  pdfMake.addVirtualFileSystem(fonts);
  pdfMake.addFonts({
    ReportBengali: {
      normal: "NotoSerifBengali-Regular.ttf",
      bold: "NotoSerifBengali-SemiBold.ttf",
      italics: "NotoSerifBengali-Regular.ttf",
      bolditalics: "NotoSerifBengali-SemiBold.ttf",
    },
  });
  return Uint8Array.from(
    await pdfMake.createPdf(reportPdfDefinition(report)).getBuffer(),
  );
}
