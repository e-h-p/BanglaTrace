import { reportHighlights } from "../reportPresentation";
import type { Match } from "../types";

export default function ColourLegend({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <section
      className={`colour-legend ${compact ? "compact" : ""}`}
      aria-label="Highlight colour key"
    >
      <h3>Highlight colour key</h3>
      <ul>
        {(
          Object.entries(reportHighlights) as [
            Match["status"],
            (typeof reportHighlights)[Match["status"]],
          ][]
        ).map(([status, item]) => (
          <li key={status} title={item.description}>
            <span className={`highlight-swatch ${status}`} aria-hidden="true" />
            <span>
              <b>{item.colour}</b> — {item.label}
            </span>
          </li>
        ))}
      </ul>
      {!compact && (
        <p>
          Colours describe verification results. Yellow is not a confirmed
          match.
        </p>
      )}
    </section>
  );
}
