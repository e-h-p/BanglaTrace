import { describe, it, expect } from "vitest";
import { textParts, evidenceRows } from "./reportUtils";
import type { Match, Report } from "./types";
const matches = [
  {
    query: {
      sentence_id: "Q1",
      sentence_number: 1,
      char_start: 2,
      char_end: 6,
    },
    sources: [],
    status: "unmatched",
  },
  {
    query: {
      sentence_id: "Q2",
      sentence_number: 2,
      char_start: 8,
      char_end: 12,
    },
    sources: [],
    status: "unverified",
  },
] as unknown as Match[];
describe("report evidence helpers", () => {
  it("preserves every original character around sentence annotations", () => {
    const text = "  বাংলা\n\nলেখা  ";
    const parts = textParts(text, matches);
    expect(parts.map((p) => p.text).join("")).toBe(text);
    expect(parts.filter((p) => p.match).length).toBe(2);
  });
  it("retains sentences with no candidates and filters by their actual status", () => {
    const report = { matches } as Report;
    expect(evidenceRows(report, "all", "", "sentence")).toHaveLength(2);
    expect(
      evidenceRows(report, "unverified", "", "sentence")[0].match.query
        .sentence_id,
    ).toBe("Q2");
    expect(evidenceRows(report, "matched", "", "sentence")).toHaveLength(0);
  });
  it("filters sources without fabricating a candidate for unmatched text", () => {
    expect(
      evidenceRows({ matches } as Report, "all", "D1", "sentence"),
    ).toHaveLength(0);
  });
});
