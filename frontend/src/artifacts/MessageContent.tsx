import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useLocale } from "@/i18n/context";
import { ArtifactBlock } from "./ArtifactBlock";
import { parseArtifactSegments } from "./parseArtifacts";
import type { ChatArtifact } from "./types";

/**
 * Render one assistant reply: prose and artifacts interleaved in source order.
 *
 * The fence positions come from parsing the raw text, but the *family* of each
 * artifact comes from the server-stamped `artifacts` list when present — that
 * is the authoritative parse. During live streaming no stamped list exists
 * yet, so a fence renders from its own header (degrading to markdown) until the
 * finished message arrives with families attached.
 */
export function MessageContent({
  content,
  artifacts,
}: {
  content: string;
  artifacts?: ChatArtifact[] | null;
}) {
  const { t } = useLocale();
  const segments = parseArtifactSegments(content);
  const stamped = artifacts ?? [];
  let stampedIndex = 0;

  // Plain reply, no fences: the overwhelmingly common case, rendered as prose.
  if (segments.length === 1 && segments[0].kind === "text") {
    return <Prose text={segments[0].text ?? ""} />;
  }

  return (
    <div className="space-y-1 text-start">
      {segments.map((segment, index) => {
        if (segment.kind === "text") {
          const text = segment.text ?? "";
          if (!text.trim()) return null;
          return <Prose key={index} text={text} />;
        }
        if (segment.kind === "artifact-open") {
          return (
            <div key={index} className="my-2 text-xs text-slate-500" data-testid="artifact-open">
              {t("artifact.streaming")}
            </div>
          );
        }
        // A closed artifact: prefer the server-stamped copy (correct family).
        const parsed = segment.artifact;
        const authoritative = stamped[stampedIndex] ?? parsed;
        stampedIndex += 1;
        if (!authoritative) return null;
        return <ArtifactBlock key={index} artifact={authoritative} />;
      })}
    </div>
  );
}

function Prose({ text }: { text: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none text-inherit">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
