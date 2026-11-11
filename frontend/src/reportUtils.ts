import type { Candidate, Match, Report } from "./types";
export function textParts(text: string, matches: Match[]) {
  // API offsets count Unicode code points (Python), not UTF-16 units (JavaScript).
  // This also keeps Bangla boundaries correct when the input contains emoji.
  const characters = Array.from(text);
  const parts: { text: string; match?: Match }[] = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.query.char_start > cursor)
      parts.push({
        text: characters.slice(cursor, match.query.char_start).join(""),
      });
    parts.push({
      text: characters
        .slice(match.query.char_start, match.query.char_end)
        .join(""),
      match,
    });
    cursor = match.query.char_end;
  }
  if (cursor < characters.length)
    parts.push({ text: characters.slice(cursor).join("") });
  return parts;
}
export function evidenceRows(
  report: Report,
  filter: string,
  source: string,
  sort: string,
) {
  const rows: { match: Match; candidate?: Candidate }[] = [];
  for (const match of report.matches) {
    if (filter !== "all" && match.status !== filter) continue;
    if (!match.sources.length && !source) rows.push({ match });
    for (const candidate of match.sources)
      if (!source || candidate.source.document_id === source)
        rows.push({ match, candidate });
  }
  return rows.sort((a, b) =>
    sort === "cosine"
      ? (b.candidate?.cosine_similarity ?? -2) -
        (a.candidate?.cosine_similarity ?? -2)
      : sort === "lcs"
        ? (b.candidate?.lcs_similarity ?? -1) -
          (a.candidate?.lcs_similarity ?? -1)
        : sort === "source"
          ? (a.candidate?.source.filename ?? "").localeCompare(
              b.candidate?.source.filename ?? "",
            )
          : a.match.query.sentence_number - b.match.query.sentence_number,
  );
}
