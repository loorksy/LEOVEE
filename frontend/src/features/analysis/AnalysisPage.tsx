import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { evidenceFromEngines, runAnalysis, type AnalysisRunResponse } from "@/api/analysis";
import { EvidencePanel } from "./EvidencePanel";
import { buildSemanticModel, persistSemanticModel } from "@/api/chart";
import { getProvidersStatus } from "@/api/providers";
import {
  ProviderNotConfiguredBanner,
  isLlmConfigured,
  llmCredentialNames,
} from "@/components/ProviderNotConfiguredBanner";
import { useLocale } from "@/i18n/context";
import type { LocaleContextValue } from "@/i18n/context";

type Translator = LocaleContextValue["t"];

/** Backend narrative is a dict (llm summary or llm_unavailable); never render raw objects. */
export function formatAnalysisNarrative(narrative: unknown, t: Translator): string | null {
  if (narrative == null) return null;
  if (typeof narrative === "string") {
    const trimmed = narrative.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof narrative !== "object") {
    return String(narrative);
  }
  const obj = narrative as Record<string, unknown>;
  if (typeof obj.llm_unavailable === "string") {
    return t("analysis.narrative.unavailable", { reason: obj.llm_unavailable });
  }
  if (typeof obj.adversarial_unavailable === "string") {
    return t("analysis.narrative.adversarialUnavailable", {
      reason: obj.adversarial_unavailable,
    });
  }
  const llm = obj.llm;
  if (llm && typeof llm === "object") {
    const summary = (llm as Record<string, unknown>).summary;
    if (typeof summary === "string" && summary.trim()) return summary;
  }
  if (typeof obj.summary === "string" && obj.summary.trim()) return obj.summary;
  try {
    return JSON.stringify(narrative);
  } catch {
    return null;
  }
}

export function getAnalysisDegradedReason(result: AnalysisRunResponse): string | null {
  const fromDecision = result.decision?.degraded_reason;
  if (typeof fromDecision === "string" && fromDecision) return fromDecision;
  const narrative = result.narrative;
  if (narrative && typeof narrative === "object") {
    const obj = narrative as Record<string, unknown>;
    if (typeof obj.degraded_reason === "string") return obj.degraded_reason;
    if (typeof obj.llm_unavailable === "string") return "LLM_UNAVAILABLE";
    if (typeof obj.adversarial_unavailable === "string") return "ADVERSARIAL_UNAVAILABLE";
  }
  return null;
}

async function tryPublishChartAnnotations(
  response: AnalysisRunResponse,
  t: Translator,
): Promise<string> {
  const { model } = await buildSemanticModel({
    symbol: response.symbol,
    timeframe: response.timeframe,
    as_of: response.as_of,
    engines: response.engines,
  });
  if (model.operations.length === 0) {
    return t("analysis.chart.none");
  }
  const persisted = await persistSemanticModel(
    { ...model, symbol: response.symbol, timeframe: response.timeframe },
    { recommendationId: response.recommendation_id },
  );
  return t("analysis.chart.published", { count: persisted.count });
}

export function AnalysisPage() {
  const { t } = useLocale();
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [completePipeline, setCompletePipeline] = useState(true);
  const [result, setResult] = useState<AnalysisRunResponse | null>(null);
  const [chartStatus, setChartStatus] = useState<string | null>(null);
  const navigate = useNavigate();

  const providersQuery = useQuery({
    queryKey: ["providers", "status"],
    queryFn: getProvidersStatus,
  });

  const oandaConfigured = providersQuery.data?.oanda.configured === true;
  const llmConfigured = providersQuery.data ? isLlmConfigured(providersQuery.data) : true;
  const providersReady = providersQuery.isSuccess;
  const canRun = oandaConfigured && llmConfigured;

  const mutation = useMutation({
    mutationFn: async () => {
      const response = await runAnalysis({
        symbol,
        complete_pipeline: completePipeline,
      });
      setResult(response);
      setChartStatus(null);
      const degraded = getAnalysisDegradedReason(response);
      if (degraded) {
        setChartStatus(null);
        return response;
      }
      try {
        const status = await tryPublishChartAnnotations(response, t);
        setChartStatus(status);
      } catch {
        setChartStatus(t("analysis.chart.error"));
      }
      return response;
    },
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">{t("analysis.title")}</h1>
        <p className="mt-1 text-slate-400">{t("analysis.intro")}</p>
      </header>

      {providersReady && !oandaConfigured && (
        <ProviderNotConfiguredBanner
          title={t("analysis.provider.marketDataMissing")}
          credentials={["OANDA_API_TOKEN", "OANDA_ACCOUNT_ID"]}
          testId="analysis-oanda-not-configured"
        />
      )}
      {providersReady && !llmConfigured && (
        <ProviderNotConfiguredBanner
          title={t("analysis.provider.llmMissing")}
          credentials={llmCredentialNames()}
          testId="analysis-llm-not-configured"
        />
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!canRun) return;
          mutation.mutate();
        }}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-800 bg-leovee-panel p-4"
      >
        <label className="text-sm text-slate-300" htmlFor="analysis-symbol">
          {t("common.symbol")}
          <input
            id="analysis-symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            disabled={!canRun}
            className="mt-1 block w-32 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={completePipeline}
            onChange={(event) => setCompletePipeline(event.target.checked)}
            disabled={!canRun}
          />
          {t("analysis.fullPipeline")}
        </label>
        <button
          type="submit"
          data-testid="analysis-run"
          disabled={mutation.isPending || !canRun}
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {mutation.isPending ? t("analysis.running") : t("analysis.run")}
        </button>
      </form>

      {mutation.isError && (
        <p className="text-amber-400" data-testid="analysis-error">
          {mutation.error instanceof Error ? mutation.error.message : t("analysis.error.failed")}
        </p>
      )}

      {result && (
        <AnalysisResult
          result={result}
          chartStatus={chartStatus}
          onViewChart={() =>
            navigate(`/analyst?symbol=${result.symbol}&timeframe=${result.timeframe}`)
          }
          onViewRecommendation={
            result.recommendation_id ? () => navigate("/recommendations") : undefined
          }
        />
      )}
    </div>
  );
}

function AnalysisResult({
  result,
  chartStatus,
  onViewChart,
  onViewRecommendation,
}: {
  result: AnalysisRunResponse;
  chartStatus: string | null;
  onViewChart: () => void;
  onViewRecommendation?: () => void;
}) {
  const { t } = useLocale();
  const degradedReason = getAnalysisDegradedReason(result);
  const narrativeText = formatAnalysisNarrative(result.narrative, t);
  const evidence = evidenceFromEngines(result.engines);

  if (degradedReason) {
    return (
      <section
        className="rounded-lg border border-amber-800/60 bg-amber-950/30 p-6"
        data-testid="analysis-degraded"
      >
        <h2 className="text-lg font-semibold text-amber-100">
          {result.symbol} · {result.timeframe} — {t("analysis.blocked")}
        </h2>
        <p className="mt-2 text-sm text-amber-100/90">
          {t("analysis.degraded.resultLabel")}: <span className="font-semibold">NO_TRADE</span> ·{" "}
          {t("analysis.degraded.reasonLabel")}{" "}
          <code className="text-amber-50">{degradedReason}</code>
        </p>
        <p className="mt-1 text-sm text-amber-200/80">{t("analysis.degraded.explanation")}</p>
        {narrativeText && <p className="mt-3 text-sm text-amber-100/80">{narrativeText}</p>}
        {evidence && <EvidencePanel report={evidence} />}
      </section>
    );
  }

  const direction = String(result.decision.direction ?? "NO_TRADE");
  const directionLabel =
    direction === "BUY"
      ? t("direction.buy")
      : direction === "SELL"
        ? t("direction.sell")
        : direction;
  const confidence =
    result.decision.confidence == null
      ? null
      : (Number(result.decision.confidence) * 100).toFixed(0);

  return (
    <section
      className="rounded-lg border border-slate-800 bg-leovee-panel p-6"
      data-testid="analysis-result"
    >
      <h2 className="text-lg font-semibold text-slate-100" data-testid="analysis-result-title">
        {result.symbol} · {result.timeframe} — {directionLabel}
      </h2>
      <p className="mt-1 text-sm text-slate-400" data-testid="analysis-result-meta">
        {confidence != null ? `${t("analysis.confidence", { value: confidence })} · ` : ""}
        {t("analysis.recalled", { count: result.recall.count })} ·{" "}
        {t("analysis.asOf", { date: result.as_of })}
      </p>
      {narrativeText && <p className="mt-3 text-sm text-slate-300">{narrativeText}</p>}
      {chartStatus && (
        <p className="mt-3 text-xs text-slate-500" data-testid="chart-status">
          {chartStatus}
        </p>
      )}
      {evidence && <EvidencePanel report={evidence} />}
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          data-testid="analysis-view-chart"
          onClick={onViewChart}
          className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
        >
          {t("analysis.viewChart")}
        </button>
        {onViewRecommendation && (
          <button
            type="button"
            data-testid="analysis-view-recommendation"
            onClick={onViewRecommendation}
            className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            {t("analysis.viewRecommendation")}
          </button>
        )}
      </div>
    </section>
  );
}
