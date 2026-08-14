import type { ChatArtifact } from "../types";

/**
 * A JSON payload, pretty-printed. If the payload is not valid JSON it is shown
 * verbatim rather than dropped — the raw text is still the agent's output, and
 * hiding it hides the bug.
 */
export function JsonArtifact({ artifact }: { artifact: ChatArtifact }) {
  let body = artifact.content;
  try {
    body = JSON.stringify(JSON.parse(artifact.content), null, 2);
  } catch {
    // Not JSON: fall through and render the raw payload.
  }
  return (
    <figure className="my-2 overflow-hidden rounded border border-slate-700 bg-slate-950">
      {artifact.title ? (
        <figcaption className="border-b border-slate-800 px-3 py-1.5 text-xs text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed text-emerald-200" dir="ltr">
        <code>{body}</code>
      </pre>
    </figure>
  );
}
