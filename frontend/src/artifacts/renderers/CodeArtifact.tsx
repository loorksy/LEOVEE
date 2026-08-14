import type { ChatArtifact } from "../types";

/**
 * Source code, one language. No client-side re-execution and no syntax
 * highlighter dependency — a monospaced block with a language label. The label
 * comes from the artifact header, not from guessing at the content.
 */
export function CodeArtifact({ artifact }: { artifact: ChatArtifact }) {
  return (
    <figure className="my-2 overflow-hidden rounded border border-slate-700 bg-slate-950">
      <figcaption className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5 text-xs text-slate-400">
        <span>{artifact.title ?? "code"}</span>
        {artifact.language ? (
          <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono">{artifact.language}</span>
        ) : null}
      </figcaption>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed text-slate-100" dir="ltr">
        <code>{artifact.content}</code>
      </pre>
    </figure>
  );
}
