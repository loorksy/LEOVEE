/**
 * Client-side parse of the artifact fence, for text still streaming over SSE.
 *
 * The server parses and stamps the authoritative copy at persist time
 * (`content_json.artifacts`); this parser exists so an artifact renders live
 * while the tokens are still arriving. The two implementations must agree on
 * the fence format exactly — the format is:
 *
 *     ```artifact
 *     {"type": "line-chart", "title": "…", "family": "chart", "language": null}
 *     …payload…
 *     ```
 *
 * One JSON header line, then the payload verbatim until the closing fence.
 * A fence still missing its closing marker is an *open* artifact: rendered as
 * in-progress rather than parsed as half a payload.
 */

import { type ArtifactFamily, type ChatArtifact, isArtifactFamily } from "./types";

const FENCE_OPEN = "```artifact";
const FENCE_CLOSE = "```";

export interface ParsedSegment {
  kind: "text" | "artifact" | "artifact-open";
  text?: string;
  artifact?: ChatArtifact;
}

function headerToArtifact(headerLine: string, payload: string): ChatArtifact {
  let type = "markdown";
  let family: ArtifactFamily = "markdown";
  let title: string | null = null;
  let language: string | null = null;
  try {
    const header = JSON.parse(headerLine) as Record<string, unknown>;
    if (typeof header.type === "string" && header.type) type = header.type;
    if (isArtifactFamily(header.family)) family = header.family;
    if (typeof header.title === "string") title = header.title;
    if (typeof header.language === "string") language = header.language;
  } catch {
    // A malformed header renders as markdown rather than vanishing: the
    // payload is still the agent's output, and hiding it hides the bug.
  }
  return { type, family, title, language, content: payload };
}

/** Split raw assistant text into plain-text and artifact segments, in order. */
export function parseArtifactSegments(raw: string): ParsedSegment[] {
  const segments: ParsedSegment[] = [];
  let cursor = 0;
  while (cursor < raw.length) {
    const open = raw.indexOf(FENCE_OPEN, cursor);
    if (open === -1) {
      const rest = raw.slice(cursor);
      if (rest) segments.push({ kind: "text", text: rest });
      break;
    }
    if (open > cursor) segments.push({ kind: "text", text: raw.slice(cursor, open) });

    const bodyStart = raw.indexOf("\n", open);
    if (bodyStart === -1) {
      // The fence marker arrived but nothing after it yet.
      segments.push({ kind: "artifact-open" });
      break;
    }
    const headerEnd = raw.indexOf("\n", bodyStart + 1);
    const close = headerEnd === -1 ? -1 : raw.indexOf(`\n${FENCE_CLOSE}`, headerEnd);
    if (headerEnd === -1 || close === -1) {
      // Header or payload still streaming.
      const headerLine = headerEnd === -1 ? raw.slice(bodyStart + 1) : raw.slice(bodyStart + 1, headerEnd);
      const payload = headerEnd === -1 ? "" : raw.slice(headerEnd + 1);
      segments.push({
        kind: "artifact-open",
        artifact: headerToArtifact(headerLine.trim(), payload),
      });
      break;
    }
    const headerLine = raw.slice(bodyStart + 1, headerEnd).trim();
    const payload = raw.slice(headerEnd + 1, close);
    segments.push({ kind: "artifact", artifact: headerToArtifact(headerLine, payload) });
    cursor = close + 1 + FENCE_CLOSE.length;
    // Swallow a single trailing newline after the closing fence.
    if (raw[cursor] === "\n") cursor += 1;
  }
  return segments;
}
