/**
 * The chart, as the chat's companion surface — not a page. Same engine
 * wiring `ChartPage` used to own directly (symbol/timeframe via URL params,
 * candles + annotations + live stream into a `ChartEngine`), relocated so it
 * can live inside the sheet/pane the merged chat workspace renders it in.
 *
 * The `TradingViewChart` DOM node this mounts is never unmounted by the
 * sheet/pane toggle around it — only CSS classes change there — so a symbol
 * change never throws away drawings on the widget.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  createChartEngine,
  TradingViewAnnotationSurface,
  type ChartEngine,
  type SemanticAnnotation,
} from "@/chart";
import { TradingViewChart } from "@/chart/tradingview/TradingViewChart";
import { resolutionForTimeframe, timeframeForResolution } from "@/chart/tradingview/datafeed";
import type { TradingViewShapeApi } from "@/chart";
import { normalizeBackendCandle } from "@/chart/ChartDataAdapter";
import { getCandles } from "@/api/markets";
import { listChartAnnotations } from "@/api/chart";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { useChartStream } from "@/features/chart/useChartStream";
import {
  annotationListToMap,
  annotationMapToList,
  applyAnnotationEvent,
} from "@/features/chart/annotationStream";
import { BACKEND_TIMEFRAMES, backendTimeframeToChart } from "@/features/chart/timeframe";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useLocale } from "@/i18n/context";
import { Input } from "@/components/ui/Input";

const DEFAULT_TIMEFRAME = "H1";

export function ChartCompanionPanel() {
  const { t } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const symbol = (searchParams.get("symbol") ?? DEFAULT_SYMBOL).toUpperCase();
  const timeframe = searchParams.get("timeframe") ?? DEFAULT_TIMEFRAME;

  const engineRef = useRef<ChartEngine | null>(null);
  const annotationsRef = useRef<Map<string, SemanticAnnotation>>(new Map());
  const [annotationCount, setAnnotationCount] = useState(0);

  const workspaceQuery = useWorkspaceId();
  const chartResolution = resolutionForTimeframe(backendTimeframeToChart(timeframe));

  const loadCandlesForChart = useCallback(
    async (requestedSymbol: string, resolution: string) => {
      const response = await getCandles(requestedSymbol, timeframeForResolution(resolution));
      return response.candles.map(normalizeBackendCandle);
    },
    [],
  );

  const candlesQuery = useQuery({
    queryKey: ["candles", symbol, timeframe],
    queryFn: () => getCandles(symbol, timeframe),
  });

  const annotationsQuery = useQuery({
    queryKey: ["chart-annotations"],
    queryFn: () => listChartAnnotations(),
  });

  const handleShapesReady = useCallback((shapes: TradingViewShapeApi) => {
    const engine = createChartEngine({ surface: new TradingViewAnnotationSurface({ shapes }) });
    engineRef.current = engine;
    engine.setSymbol(symbol);
    engine.setTimeframe(backendTimeframeToChart(timeframe));
    if (candlesQuery.data) {
      engine.applyCandles(candlesQuery.data.candles.map(normalizeBackendCandle));
    }
    if (annotationsRef.current.size) {
      engine.applyAnnotations(annotationMapToList(annotationsRef.current));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      engineRef.current?.destroy();
      engineRef.current = null;
    };
  }, []);

  useEffect(() => {
    engineRef.current?.setSymbol(symbol);
    engineRef.current?.setTimeframe(backendTimeframeToChart(timeframe));
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!candlesQuery.data) return;
    engineRef.current?.applyCandles(candlesQuery.data.candles.map(normalizeBackendCandle));
  }, [candlesQuery.data]);

  useEffect(() => {
    if (!annotationsQuery.data) return;
    annotationsRef.current = annotationListToMap(annotationsQuery.data.items);
    engineRef.current?.applyAnnotations(annotationMapToList(annotationsRef.current));
    setAnnotationCount(annotationsRef.current.size);
  }, [annotationsQuery.data]);

  useChartStream({
    symbol,
    workspaceId: workspaceQuery.data,
    onCandle: (candle) => {
      engineRef.current?.applyCandlePatch(normalizeBackendCandle(candle));
    },
    onAnnotationEvent: (event) => {
      annotationsRef.current = applyAnnotationEvent(annotationsRef.current, event);
      engineRef.current?.applyAnnotations(annotationMapToList(annotationsRef.current));
      setAnnotationCount(annotationsRef.current.size);
    },
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="chart-symbol">
          {t("common.symbol")}
          <Input
            id="chart-symbol"
            data-testid="chart-symbol-input"
            className="h-9 w-28"
            value={symbol}
            onChange={(event) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set("symbol", event.target.value.toUpperCase());
                return next;
              })
            }
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="chart-timeframe">
          {t("common.timeframe")}
          <select
            id="chart-timeframe"
            data-testid="chart-timeframe-select"
            className="h-9 w-24 rounded-md border border-border bg-input px-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            value={timeframe}
            onChange={(event) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set("timeframe", event.target.value);
                return next;
              })
            }
          >
            {BACKEND_TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <p className="ms-auto text-xs text-muted-foreground" data-testid="annotation-count">
          {t("chart.annotations.count", { count: annotationCount })}
        </p>
      </div>
      {candlesQuery.isError && (
        <p className="text-sm text-destructive">{t("chart.error.candles", { symbol })}</p>
      )}
      <div
        data-testid="chart-container"
        className="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-card"
      >
        <TradingViewChart
          symbol={symbol}
          resolution={chartResolution}
          loadCandles={loadCandlesForChart}
          onShapesReady={handleShapesReady}
        />
      </div>
    </div>
  );
}
