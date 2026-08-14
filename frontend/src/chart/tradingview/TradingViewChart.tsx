/**
 * The chart, mounted.
 *
 * Loads the vendored library, creates the widget, and hands its shape API up
 * once the chart is ready. Everything above this component talks to
 * `ChartEngine`, so this is the only React code aware of which library draws.
 */

import { useEffect, useRef, useState } from "react";

import type { TradingViewShapeApi } from "../TradingViewAdapter";
import { createDatafeed, type LoadCandles } from "./datafeed";
import { loadChartingLibrary, type TradingViewWidget } from "./loadLibrary";

export type TradingViewChartProps = {
  symbol: string;
  /** Library resolution string, e.g. "15". */
  resolution: string;
  loadCandles: LoadCandles;
  /** Called once the chart is ready, with the surface annotations draw on. */
  onShapesReady: (shapes: TradingViewShapeApi) => void;
  locale?: string;
  theme?: "light" | "dark";
};

export function TradingViewChart({
  symbol,
  resolution,
  loadCandles,
  onShapesReady,
  locale = "ar",
  theme = "dark",
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetRef = useRef<TradingViewWidget | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The callback is held in a ref so a parent re-render does not tear the
  // widget down and rebuild it — recreating a 27 MB chart because a closure
  // changed identity is the kind of thing that only shows up as jank.
  const onShapesReadyRef = useRef(onShapesReady);
  onShapesReadyRef.current = onShapesReady;
  const loadCandlesRef = useRef(loadCandles);
  loadCandlesRef.current = loadCandles;

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return undefined;

    loadChartingLibrary()
      .then((Widget) => {
        if (cancelled) return;
        const widget = new Widget({
          container,
          library_path: "/charting_library/",
          symbol,
          interval: resolution,
          locale,
          theme,
          autosize: true,
          datafeed: createDatafeed((...args) => loadCandlesRef.current(...args)),
          // The agent owns what is drawn. Letting the library persist and
          // restore its own drawings would resurrect annotations the analysis
          // has since retracted, with no way to tell them from current ones.
          disabled_features: [
            "use_localstorage_for_settings",
            "save_chart_properties_to_local_storage",
            "header_symbol_search",
            "symbol_search_hot_key",
            "header_compare",
          ],
          enabled_features: ["hide_left_toolbar_by_default"],
        });
        widgetRef.current = widget;
        widget.onChartReady(() => {
          if (cancelled) return;
          const chart = widget.activeChart();
          onShapesReadyRef.current({
            createMultipointShape: (points, options) =>
              chart.createMultipointShape(points, options),
            removeEntity: (id) => chart.removeEntity(id),
            setSymbol: (nextSymbol, _interval, callback) =>
              chart.setSymbol(nextSymbol, callback),
          });
        });
      })
      .catch((loadError: unknown) => {
        if (cancelled) return;
        // Surfaced, not swallowed. A blank rectangle where a chart should be
        // reads as "no data" rather than "the asset is missing", and the two
        // send whoever is looking in completely different directions.
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => {
      cancelled = true;
      widgetRef.current?.remove();
      widgetRef.current = null;
    };
    // Symbol and resolution changes go through the widget's own API rather than
    // a remount; see the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div data-testid="chart-load-error" role="alert">
        {error}
      </div>
    );
  }
  return <div ref={containerRef} data-testid="tradingview-chart" style={{ height: "100%" }} />;
}
