import { Component, type ReactNode, Suspense, lazy } from "react";
import { useLocale } from "@/i18n/context";
import type { ChatArtifact } from "./types";
import { CodeArtifact } from "./renderers/CodeArtifact";
import { JsonArtifact } from "./renderers/JsonArtifact";
import { MarkdownArtifact } from "./renderers/MarkdownArtifact";
import { TableArtifact } from "./renderers/TableArtifact";
import { WebArtifact } from "./renderers/WebArtifact";

// The three heavy renderers pull in charting / diagram libraries; they are
// split out so a conversation with no chart never downloads them.
const ChartArtifact = lazy(() =>
  import("./renderers/ChartArtifact").then((m) => ({ default: m.ChartArtifact })),
);
const CandlestickArtifact = lazy(() =>
  import("./renderers/CandlestickArtifact").then((m) => ({ default: m.CandlestickArtifact })),
);
const MermaidArtifact = lazy(() =>
  import("./renderers/MermaidArtifact").then((m) => ({ default: m.MermaidArtifact })),
);

/** A crashing renderer must not take the conversation down with it: the payload
 *  is still the agent's output, so a failed render falls back to raw text. */
class RendererBoundary extends Component<
  { fallbackNote: string; content: string; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <figure className="my-2 rounded border border-amber-800 bg-slate-900 p-3">
          <figcaption className="mb-1 text-xs text-amber-400">{this.props.fallbackNote}</figcaption>
          <pre className="overflow-x-auto text-xs text-slate-300" dir="ltr">
            <code>{this.props.content}</code>
          </pre>
        </figure>
      );
    }
    return this.props.children;
  }
}

function renderFamily(artifact: ChatArtifact): ReactNode {
  switch (artifact.family) {
    case "table":
      return <TableArtifact artifact={artifact} />;
    case "code":
      return <CodeArtifact artifact={artifact} />;
    case "json":
      return <JsonArtifact artifact={artifact} />;
    case "web":
      return <WebArtifact artifact={artifact} />;
    case "mermaid":
      return <MermaidArtifact artifact={artifact} />;
    case "chart": {
      const kind = artifact.type.toLowerCase();
      const isCandles = kind.includes("candlestick") || kind.includes("trading-view");
      return isCandles ? (
        <CandlestickArtifact artifact={artifact} />
      ) : (
        <ChartArtifact artifact={artifact} />
      );
    }
    case "markdown":
    default:
      return <MarkdownArtifact artifact={artifact} />;
  }
}

export function ArtifactBlock({ artifact }: { artifact: ChatArtifact }) {
  const { t } = useLocale();
  return (
    <RendererBoundary fallbackNote={t("artifact.error")} content={artifact.content}>
      <Suspense
        fallback={<div className="my-2 text-xs text-slate-500">{t("artifact.loading")}</div>}
      >
        {renderFamily(artifact)}
      </Suspense>
    </RendererBoundary>
  );
}
