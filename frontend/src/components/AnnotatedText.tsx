import type { Match } from "../types";
import { textParts } from "../reportUtils";
import { reportHighlights } from "../reportPresentation";

export default function AnnotatedText({
  text,
  matches,
  selectedId,
  onSelect,
}: {
  text: string;
  matches: Match[];
  selectedId?: string;
  onSelect: (match: Match) => void;
}) {
  return (
    <div
      className="annotated-text"
      lang="bn"
      aria-label="Input text with sentence highlights"
    >
      {textParts(text, matches).map((part, i) =>
        part.match ? (
          <span
            key={part.match.query.sentence_id}
            role="button"
            tabIndex={0}
            className={`sentence ${part.match.status} ${selectedId === part.match.query.sentence_id ? "selected" : ""}`}
            aria-label={`Sentence ${part.match.query.sentence_number}: ${reportHighlights[part.match.status].label}`}
            aria-pressed={selectedId === part.match.query.sentence_id}
            title={`${reportHighlights[part.match.status].colour}: ${reportHighlights[part.match.status].description}`}
            onClick={() => onSelect(part.match!)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(part.match!);
              }
            }}
          >
            {part.text}
          </span>
        ) : (
          <span key={`gap-${i}`}>{part.text}</span>
        ),
      )}
    </div>
  );
}
