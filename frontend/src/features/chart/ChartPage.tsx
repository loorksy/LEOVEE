import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  createChartEngine,
  TradingViewAnnotationSurface,
  type ChartEngine,
  type SemanticAnnotation,
} from "@/chart";
import { TradingViewChart } from "@/chart/tradingview/TradingViewChart";
import {
  resolutionForTimeframe,
  timeframeForResolution,
} from "@/chart/tradingview/datafeed";
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
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";


const DEFAULT_TIMEFRAME = "H1";

export function ChartPage() {
  const { t } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const symbol = (searchParams.get("symbol") ?? DEFAULT_SYMBOL).toUpperCase();
  const timeframe = searchParams.get("timeframe") ?? DEFAULT_TIMEFRAME;

  const engineRef = useRef<ChartEngine | null>(null);
  const annotationsRef = useRef<Map<string, SemanticAnnotation>>(new Map());
  const [annotationCount, setAnnotationCount] = useState(0);

  const workspaceQuery = useWorkspaceId();
  const chartResolution = resolutionForTimeframe(backendTimeframeToChart(timeframe));

  // The library asks for history by its own resolution string; the API speaks
  // frame codes. Translating here keeps the mapping in one direction and one
  // place — two translations of the same pair drift, and the symptom is a chart
  // that quietly renders the wrong frame.
  const loadCandlesForChart = useCallback(
    async (requestedSymbol: string, resolution: string) => {
      const response = await getCandles(
        requestedSymbol,
        timeframeForResolution(resolution),
      );
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

  // The engine is created when the chart hands over its drawing surface, not on
  // mount: an engine with nowhere to draw would silently accept annotations and
  // discard them, which looks exactly like an analysis that produced none.
  const handleShapesReady = useCallback((shapes: TradingViewShapeApi) => {
    const engine = createChartEngine({
      surface: new TradingViewAnnotationSurface({ shapes }),
    });
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
    <div className="flex min-h-0 flex-1 flex-col gap-4 p-4">
      <PageHeader testId="chart-title" title={t("chart.title")} />
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="chart-symbol">
          {t("common.symbol")}
          <Input
            id="chart-symbol"
            data-testid="chart-symbol-input"
            className="sm:w-40"
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
            className="h-11 rounded-md border border-border bg-input px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 sm:h-9 sm:w-28"
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
      </div>
      {candlesQuery.isError && (
        <p className="text-sm text-destructive">{t("chart.error.candles", { symbol })}</p>
      )}
      <Card data-testid="chart-container" className="min-h-[420px] flex-1 overflow-hidden">
        <TradingViewChart
          symbol={symbol}
          resolution={chartResolution}
          loadCandles={loadCandlesForChart}
          onShapesReady={handleShapesReady}
        />
      </Card>
      <p className="text-xs text-muted-foreground" data-testid="annotation-count">
        {t("chart.annotations.count", { count: annotationCount })}
      </p>
    </div>
  );
}
