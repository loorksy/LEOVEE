import { useEffect, useRef, useState } from "react";
import type { ChatArtifact } from "../types";

let _idSeq = 0;

/**
 * A Mermaid diagram (flowchart, sequence, mindmap, …). Mermaid is imported
 * inside the effect so the parser stays out of any path that never renders a
 * diagram, and a syntax error surfaces the offending source rather than a
 * blank box.
 */
export function MermaidArtifact({ artifact }: { artifact: ChatArtifact }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    void import("mermaid").then(async ({ default: mermaid }) => {
      if (disposed) return;
      mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
      const id = `mermaid-${(_idSeq += 1)}`;
      try {
        const { svg } = await mermaid.render(id, artifact.content.trim());
        if (!disposed && ref.current) {
          ref.current.innerHTML = svg;
          setError(null);
        }
      } catch (err) {
        if (!disposed) setError(err instanceof Error ? err.message : "diagram error");
      }
    });
    return () => {
      disposed = true;
    };
  }, [artifact.content]);

  return (
    <figure className="my-2 rounded border border-slate-700 bg-slate-900 p-3">
      {artifact.title ? (
        <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      {error ? (
        <pre className="overflow-x-auto text-xs text-amber-400" dir="ltr">
          <code>{artifact.content}</code>
        </pre>
      ) : (
        <div ref={ref} className="flex justify-center" dir="ltr" data-testid="mermaid-container" />
      )}
    </figure>
  );
}
