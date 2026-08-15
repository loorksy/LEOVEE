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
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";

// Same visual treatment as <Card> (rounded-xl border border-border bg-card),
// but as a semantic <section> — the result and degraded panels are addressed
// by section-relative queries elsewhere (App.e2e.test.tsx), so the element
// itself must stay a <section>, not Card's <div>.
const RESULT_SECTION_CLASS = "rounded-xl border border-border bg-card text-card-foreground";

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
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6">
      <PageHeader
        title={t("analysis.title")}
        description={t("analysis.intro")}
        testId="analysis-title"
      />

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
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:flex-row sm:flex-wrap sm:items-end"
      >
        <label className="flex flex-col gap-1 text-sm text-muted-foreground sm:w-36" htmlFor="analysis-symbol">
          {t("common.symbol")}
          <Input
            id="analysis-symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            disabled={!canRun}
            className="font-mono uppercase tracking-wide"
          />
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm text-muted-foreground sm:min-h-0">
          <input
            type="checkbox"
            checked={completePipeline}
            onChange={(event) => setCompletePipeline(event.target.checked)}
            disabled={!canRun}
            className="size-4 shrink-0 rounded border-border accent-primary disabled:opacity-50"
          />
          {t("analysis.fullPipeline")}
        </label>
        <Button
          type="submit"
          data-testid="analysis-run"
          disabled={mutation.isPending || !canRun}
          className="w-full sm:ms-auto sm:w-auto"
        >
          {mutation.isPending ? t("analysis.running") : t("analysis.run")}
        </Button>
      </form>

      {mutation.isError && (
        <p className="text-sm text-destructive" data-testid="analysis-error">
          {mutation.error instanceof Error ? mutation.error.message : t("analysis.error.failed")}
        </p>
      )}

      {result && (
        <AnalysisResult
          result={result}
          chartStatus={chartStatus}
          onViewChart={() =>
            navigate(`/chat?symbol=${result.symbol}&timeframe=${result.timeframe}&chart=1`)
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
        className={cn(RESULT_SECTION_CLASS, "border-warning/30 bg-warning/10 p-4 sm:p-6")}
        data-testid="analysis-degraded"
      >
        <h2 className="break-words text-lg font-semibold text-foreground">
          <span className="font-mono">{result.symbol}</span> · {result.timeframe} —{" "}
          {t("analysis.blocked")}
        </h2>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-foreground/90">
          <span>{t("analysis.degraded.resultLabel")}:</span>
          <Badge variant="warning">NO_TRADE</Badge>
          <span>{t("analysis.degraded.reasonLabel")}</span>
          <code className="font-mono text-warning">{degradedReason}</code>
        </p>
        <p className="mt-1 text-sm text-muted-foreground">{t("analysis.degraded.explanation")}</p>
        {narrativeText && <p className="mt-3 text-sm text-foreground/90">{narrativeText}</p>}
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
  const directionBadgeVariant = direction === "BUY" ? "buy" : direction === "SELL" ? "sell" : "neutral";
  const confidence =
    result.decision.confidence == null
      ? null
      : (Number(result.decision.confidence) * 100).toFixed(0);

  return (
    <section className={cn(RESULT_SECTION_CLASS, "p-4 sm:p-6")} data-testid="analysis-result">
      <h2
        className="flex flex-wrap items-center gap-2 text-lg font-semibold text-foreground"
        data-testid="analysis-result-title"
      >
        <span>
          <span className="font-mono">{result.symbol}</span> · {result.timeframe}
        </span>
        <Badge variant={directionBadgeVariant}>{directionLabel}</Badge>
      </h2>
      <p className="mt-1 text-sm text-muted-foreground" data-testid="analysis-result-meta">
        {confidence != null ? `${t("analysis.confidence", { value: confidence })} · ` : ""}
        {t("analysis.recalled", { count: result.recall.count })} ·{" "}
        {t("analysis.asOf", { date: result.as_of })}
      </p>
      {narrativeText && <p className="mt-3 text-sm text-foreground/90">{narrativeText}</p>}
      {chartStatus && (
        <p className="mt-3 text-xs text-muted-foreground" data-testid="chart-status">
          {chartStatus}
        </p>
      )}
      {evidence && <EvidencePanel report={evidence} />}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button type="button" variant="outline" data-testid="analysis-view-chart" onClick={onViewChart}>
          {t("analysis.viewChart")}
        </Button>
        {onViewRecommendation && (
          <Button
            type="button"
            variant="outline"
            data-testid="analysis-view-recommendation"
            onClick={onViewRecommendation}
          >
            {t("analysis.viewRecommendation")}
          </Button>
        )}
      </div>
    </section>
  );
}
