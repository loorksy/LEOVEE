import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatArtifact } from "../types";

/** Split one delimited line, honouring neither quotes nor escapes — the agent
 *  emits simple grids, and a full CSV parser would be dead weight here. */
function splitRow(line: string, delimiter: string): string[] {
  return line.split(delimiter).map((cell) => cell.trim());
}

/** Parse a CSV/TSV payload into header + rows. Returns null when the shape is
 *  not a grid, so the caller can fall back to markdown. */
function parseDelimited(text: string): { header: string[]; rows: string[][] } | null {
  const lines = text.split("\n").filter((line) => line.trim().length > 0);
  if (lines.length < 1) return null;
  const delimiter = lines[0].includes("\t") ? "\t" : ",";
  if (!lines[0].includes(delimiter)) return null;
  const header = splitRow(lines[0], delimiter);
  const rows = lines.slice(1).map((line) => splitRow(line, delimiter));
  return { header, rows };
}

export function TableArtifact({ artifact }: { artifact: ChatArtifact }) {
  const content = artifact.content.trim();
  // A markdown table (pipe-delimited) already renders well through GFM; a bare
  // CSV/TSV does not, so it is parsed into a grid here.
  const isMarkdownTable = content.includes("|");
  const grid = isMarkdownTable ? null : parseDelimited(content);

  return (
    <figure className="my-2 overflow-x-auto rounded border border-slate-700 bg-slate-900 p-3">
      {artifact.title ? (
        <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          {artifact.title}
        </figcaption>
      ) : null}
      {grid ? (
        <table className="w-full border-collapse text-sm text-slate-100">
          <thead>
            <tr>
              {grid.header.map((cell, index) => (
                <th
                  key={index}
                  className="border-b border-slate-700 px-2 py-1 text-start font-semibold text-slate-300"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-b border-slate-800 px-2 py-1">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="prose prose-invert prose-sm max-w-none text-slate-100">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )}
    </figure>
  );
}
