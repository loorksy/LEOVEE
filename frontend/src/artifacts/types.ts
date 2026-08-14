/**
 * Chat artifacts: typed, rich outputs the agent can emit inline in a reply.
 *
 * The contract is deliberately two-level. The agent speaks in *types* — a wide,
 * open-ended taxonomy ("candlestick-chart", "flowchart", "invoice", …) — while
 * the UI renders by *family*: a small, closed set of real renderers. The server
 * stamps the family on every artifact, so adding a type is a backend mapping
 * entry, never a new frontend component. That is the same open-endedness rule
 * as the locale layer: capacity to grow without a component nobody revisits.
 *
 * A type without a real renderer behind it would be fabricated capability —
 * the one thing this product never ships — so every family below is a working
 * renderer, and unknown types degrade to `markdown`, visibly, not silently.
 */

export const ARTIFACT_FAMILIES = [
  "markdown",
  "table",
  "chart",
  "mermaid",
  "code",
  "json",
  "web",
] as const;

export type ArtifactFamily = (typeof ARTIFACT_FAMILIES)[number];

export interface ChatArtifact {
  /** The agent's vocabulary, e.g. "line-chart", "invoice", "flowchart". */
  type: string;
  /** Which renderer draws it. Stamped by the server; inferred client-side
   *  only for in-flight streaming text that the server has not parsed yet. */
  family: ArtifactFamily;
  title: string | null;
  /** For `code`: the syntax name. Ignored by other families. */
  language: string | null;
  /** The raw payload between the fence header and the closing fence. */
  content: string;
}

export function isArtifactFamily(value: unknown): value is ArtifactFamily {
  return (
    typeof value === "string" && (ARTIFACT_FAMILIES as readonly string[]).includes(value)
  );
}
