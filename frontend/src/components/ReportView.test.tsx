// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReportView from "./ReportView";
import { downloadReport, reportHtml } from "../reportExport";
import { reportFixture } from "../test/reportFixture";
import * as pdfExport from "../reportPdf";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("readable report and exports", () => {
  it("keeps paragraphs, spaces, tabs and emoji exactly as supplied without atomic sentence buttons", () => {
    const report = reportFixture();
    render(<ReportView report={report} back={() => {}} />);
    const text = screen.getByLabelText("Input text with sentence highlights");
    expect(text.textContent).toBe(report.query_text);
    expect(text.querySelectorAll("button, br")).toHaveLength(0);
    expect(text.querySelectorAll("span[role=button]")).toHaveLength(4);
    expect(text.querySelector(".matched")?.textContent).toBe(
      report.matches[0].query.original_text,
    );
    for (const name of ["Red", "Orange", "Yellow", "None"])
      expect(screen.getByText(name)).toBeDefined();
  });

  it("keeps sentence evidence keyboard-accessible", async () => {
    render(<ReportView report={reportFixture()} back={() => {}} />);
    const user = userEvent.setup();
    const sentence = screen.getByRole("button", {
      name: "Sentence 2: Partial / needs review",
    });
    sentence.focus();
    await user.keyboard("{Enter}");
    expect(sentence.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("INPUT SENTENCE 2")).toBeDefined();
  });

  it("places a readable report download beside Print / Save PDF and keeps JSON", () => {
    render(<ReportView report={reportFixture()} back={() => {}} />);
    const print = screen.getByRole("button", { name: "Print / Save PDF" });
    expect(print.nextElementSibling?.textContent).toContain("Download PDF");
    expect(
      screen.getByRole("link", { name: "Download JSON" }).getAttribute("href"),
    ).toBe("/api/reports/report-fixture/download");
  });

  it("exports the same original text, all four colours and every candidate even when displayed filters differ", () => {
    const report = reportFixture();
    const document = new DOMParser().parseFromString(
      reportHtml(report),
      "text/html",
    );
    expect(document.querySelector(".annotated-text")?.textContent).toBe(
      report.query_text,
    );
    expect(document.querySelectorAll(".annotated-text .sentence")).toHaveLength(
      4,
    );
    expect(document.querySelectorAll("tbody tr")).toHaveLength(4);
    expect(document.querySelector(".sentence.unverified")?.textContent).toBe(
      report.matches[2].query.original_text,
    );
    expect(document.querySelector(".colour-legend")?.textContent).toContain(
      "Yellow — Unverified",
    );
    expect(document.querySelector("style")?.textContent).toContain(
      "box-decoration-break: clone",
    );
  });

  it("escapes user text, source filenames and provider reasons in downloaded HTML", () => {
    const report = reportFixture();
    report.query_filename = '<img src=x onerror="alert(1)">';
    report.query_text = '<script>alert("x")</script>\n\nবাংলা লেখা।';
    report.matches = [];
    const document = new DOMParser().parseFromString(
      reportHtml(report),
      "text/html",
    );
    expect(document.querySelector("h1")?.textContent).toBe(
      report.query_filename,
    );
    expect(document.querySelector(".annotated-text")?.textContent).toBe(
      report.query_text,
    );
    expect(document.querySelectorAll("script,img")).toHaveLength(0);
    expect(
      document
        .querySelector('meta[http-equiv="Content-Security-Policy"]')
        ?.getAttribute("content"),
    ).toContain("default-src 'none'");
    const sourceReport = reportFixture();
    sourceReport.matches[0].sources[0].source.filename =
      '<img src=x onerror="alert(1)">';
    sourceReport.matches[0].sources[0].verification.reason =
      '<script>alert("private")</script>';
    const evidence = new DOMParser().parseFromString(
      reportHtml(sourceReport),
      "text/html",
    );
    expect(evidence.querySelectorAll("script,img")).toHaveLength(0);
    expect(evidence.querySelector("tbody")?.textContent).toContain(
      sourceReport.matches[0].sources[0].source.filename,
    );
    expect(evidence.querySelector("tbody")?.textContent).toContain(
      sourceReport.matches[0].sources[0].verification.reason,
    );
  });

  it("downloads a PDF binary and releases its temporary URL", async () => {
    vi.spyOn(pdfExport, "renderReportPdf").mockResolvedValue(
      new TextEncoder().encode("%PDF-1.3\nfixture"),
    );
    const create = vi.fn(() => "blob:report-fixture");
    const revoke = vi.fn();
    vi.stubGlobal(
      "URL",
      Object.assign(class {}, {
        createObjectURL: create,
        revokeObjectURL: revoke,
      }),
    );
    let filename = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      filename = this.download;
    });
    vi.useFakeTimers();
    try {
      await downloadReport(reportFixture());
      expect(create.mock.calls).toHaveLength(1);
      const blob = (create.mock.calls[0] as unknown as [Blob])[0];
      expect(blob.type).toBe("application/pdf");
      expect(filename).toBe("banglatrace-report-report-fixture.pdf");
      vi.advanceTimersByTime(1000);
      expect(revoke).toHaveBeenCalledWith("blob:report-fixture");
    } finally {
      vi.useRealTimers();
    }
  });
});
