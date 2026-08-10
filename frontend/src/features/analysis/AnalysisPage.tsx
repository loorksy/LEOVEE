import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { runAnalysis, type AnalysisRunResponse } from "@/api/analysis";
import { buildSemanticModel, persistSemanticModel } from "@/api/chart";
import { BACKEND_TIMEFRAMES } from "@/features/chart/timeframe";

async function tryPublishChartAnnotations(response: AnalysisRunResponse): Promise<string> {
  const { model } = await buildSemanticModel({
    symbol: response.symbol,
    timeframe: response.timeframe,
    as_of: response.as_of,
    engines: response.engines,
  });
  if (model.operations.length === 0) {
    return "No chart annotations generated for this run.";
  }
  const persisted = await persistSemanticModel(
    { ...model, symbol: response.symbol, timeframe: response.timeframe },
    { recommendationId: response.recommendation_id },
  );
  return `${persisted.count} chart annotation(s) published to the live chart.`;
}

export function AnalysisPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState("H1");
  const [completePipeline, setCompletePipeline] = useState(true);
  const [result, setResult] = useState<AnalysisRunResponse | null>(null);
  const [chartStatus, setChartStatus] = useState<string | null>(null);
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: async () => {
      const response = await runAnalysis({
        symbol,
        timeframe,
        complete_pipeline: completePipeline,
      });
      setResult(response);
      setChartStatus(null);
      try {
        const status = await tryPublishChartAnnotations(response);
        setChartStatus(status);
      } catch {
        setChartStatus("Chart annotations could not be generated for this run.");
      }
      return response;
    },
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Analysis</h1>
        <p className="mt-1 text-slate-400">
          Run the perception → memory recall → decision pipeline for a symbol.
        </p>
      </header>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-800 bg-leovee-panel p-4"
      >
        <label className="text-sm text-slate-300" htmlFor="analysis-symbol">
          Symbol
          <input
            id="analysis-symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            className="mt-1 block w-32 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          />
        </label>
        <label className="text-sm text-slate-300" htmlFor="analysis-timeframe">
          Timeframe
          <select
            id="analysis-timeframe"
            value={timeframe}
            onChange={(event) => setTimeframe(event.target.value)}
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          >
            {BACKEND_TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={completePipeline}
            onChange={(event) => setCompletePipeline(event.target.checked)}
          />
          Full pipeline (reasoning → recommendation → thesis)
        </label>
        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {mutation.isPending ? "Running…" : "Run analysis"}
        </button>
      </form>

      {mutation.isError && (
        <p className="text-amber-400">
          {mutation.error instanceof Error ? mutation.error.message : "Analysis failed."}
        </p>
      )}

      {result && (
        <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
          <h2 className="text-lg font-semibold text-slate-100">
            {result.symbol} · {result.timeframe} — {String(result.decision.direction ?? "N/A")}
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Confidence {(Number(result.decision.confidence ?? 0) * 100).toFixed(0)}% · recalled{" "}
            {result.recall.count} memories · as of {result.as_of}
          </p>
          {result.narrative && <p className="mt-3 text-sm text-slate-300">{result.narrative}</p>}
          {chartStatus && (
            <p className="mt-3 text-xs text-slate-500" data-testid="chart-status">
              {chartStatus}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() =>
                navigate(`/analyst?symbol=${result.symbol}&timeframe=${result.timeframe}`)
              }
              className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              View chart
            </button>
            {result.recommendation_id && (
              <button
                type="button"
                onClick={() => navigate("/recommendations")}
                className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
              >
                View recommendation
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
