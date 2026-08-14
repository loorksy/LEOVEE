import type { ChatArtifact } from "../types";

/**
 * A self-contained HTML document, rendered in a sandboxed iframe. The sandbox
 * grants scripts (interactive widgets are the point) but withholds
 * same-origin, so the document cannot reach the app's storage, cookies or
 * DOM — a hostile payload is confined to its own frame.
 */
export function WebArtifact({ artifact }: { artifact: ChatArtifact }) {
  return (
    <figure className="my-2 overflow-hidden rounded border border-slate-700 bg-white">
      {artifact.title ? (
        <figcaption className="border-b border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      <iframe
        title={artifact.title ?? "web artifact"}
        sandbox="allow-scripts"
        srcDoc={artifact.content}
        className="h-80 w-full border-0"
      />
    </figure>
  );
}
