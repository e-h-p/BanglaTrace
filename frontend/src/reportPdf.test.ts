// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { reportFixture } from "./test/reportFixture";
import { reportPdfDefinition, renderReportPdf } from "./reportPdf";

afterEach(() => vi.unstubAllGlobals());

describe("direct PDF report export", () => {
  it("preserves text and colour meanings in the PDF document definition", () => {
    const report = reportFixture();
    const definition = reportPdfDefinition(report);
    const content = definition.content as {
      text?: unknown;
      fontSize?: number;
    }[];
    const input = content.find((node) => node.fontSize === 12)!;
    expect(
      (input.text as { text: string }[]).map((part) => part.text).join(""),
    ).toBe(report.query_text);
    const data = JSON.stringify(definition);
    for (const colour of ["#fde8e8", "#ffeddf", "#fff4bd"])
      expect(data).toContain(colour);
    expect(data).toContain("Rivers.txt");
    expect(data).toContain("No verified match");
  });

  it("generates an actual PDF with bundled Bengali fonts and multiple pages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        expect(url).toMatch(
          /^\/assets\/moulik\/fonts\/NotoSerifBengali-(Regular|SemiBold)\.ttf$/,
        );
        const font = await readFile(resolve("public", url.replace(/^\//, "")));
        return new Response(font);
      }),
    );
    const report = reportFixture();
    report.query_text = report.query_text.replace("🌿 ", "");
    for (const match of report.matches) {
      const start = Array.from(
        report.query_text.slice(
          0,
          report.query_text.indexOf(match.query.original_text),
        ),
      ).length;
      match.query.char_start = start;
      match.query.char_end =
        start + Array.from(match.query.original_text).length;
    }
    const pdf = await renderReportPdf(report);
    expect(new TextDecoder().decode(pdf.subarray(0, 5))).toBe("%PDF-");
    expect(pdf.byteLength).toBeGreaterThan(10000);
    expect(fetch).toHaveBeenCalledTimes(2);
    const serialized = new TextDecoder("latin1").decode(pdf);
    expect(
      serialized.match(/\/Type\s*\/Page\b/g)?.length,
    ).toBeGreaterThanOrEqual(2);
    expect(serialized).toContain("/FontFile2");
    if (process.env.PDF_QA_OUTPUT) {
      await mkdir(dirname(process.env.PDF_QA_OUTPUT), { recursive: true });
      await writeFile(process.env.PDF_QA_OUTPUT, pdf);
    }
  }, 20000);
});
