import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatArtifact } from "../types";

/**
 * Prose, reports, letters, plans — and the default renderer for any type
 * without a dedicated family, so an unknown type degrades to readable markdown
 * rather than vanishing. GitHub-flavoured markdown gives it tables, task lists
 * and strikethrough without a bespoke parser.
 */
export function MarkdownArtifact({ artifact }: { artifact: ChatArtifact }) {
  return (
    <figure className="my-2 rounded border border-slate-700 bg-slate-900 p-3">
      {artifact.title ? (
        <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      <div className="prose prose-invert prose-sm max-w-none text-slate-100">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown>
      </div>
    </figure>
  );
}
