import type { Match } from "./types";

export const reportHighlights: Record<
  Match["status"],
  {
    label: string;
    colour: string;
    description: string;
  }
> = {
  matched: {
    label: "Verified match",
    colour: "Red",
    description: "At least one source was verified as equivalent in meaning.",
  },
  partial: {
    label: "Partial / needs review",
    colour: "Orange",
    description:
      "A partial relationship was verified; review the source evidence.",
  },
  unverified: {
    label: "Unverified",
    colour: "Yellow",
    description:
      "Not confirmed: preview only, an uncertain result or an unfinished check.",
  },
  unmatched: {
    label: "No verified match",
    colour: "None",
    description:
      "No verified match among the retrieved sources; the text has no highlight.",
  },
};

/** Shared by the screen, printed report and self-contained HTML download. */
export { default as reportHighlightCss } from "./reportHighlights.css?raw";
