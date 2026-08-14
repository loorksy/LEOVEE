/**
 * Assembling the chart engine. The only place the pieces meet.
 *
 * `createChartEngine` returns the renderer-neutral `ChartEngine` contract, so
 * every consumer above this line is unaware of which library draws. Swapping
 * KLineChart for TradingView (ADR 0004) touched this file and
 * `TradingViewAdapter.ts`, and nothing else — which is the property the
 * abstraction exists to buy, and the one to protect.
 */

import { ChartAnnotationRenderer } from "./ChartAnnotationRenderer";
import { ChartCandleAdapter } from "./ChartCandleAdapter";
import { ChartController } from "./ChartController";
import type {
  AnnotationSurface,
  ChartEngine,
  NormalizedCandle,
  SemanticAnnotation,
} from "./ChartTypes";
import {
  TradingViewAnnotationSurface,
  type TradingViewShapeApi,
} from "./TradingViewAdapter";

export type CreateChartEngineOptions = {
  /**
   * The drawing surface. Injected rather than constructed here so a test — and
   * a future renderer — can supply its own without this module importing a
   * charting library at all.
   */
  surface: AnnotationSurface;
  onCandles?: (candles: NormalizedCandle[]) => void;
};

export function createChartEngine(options: CreateChartEngineOptions): ChartEngine {
  const adapter = new ChartCandleAdapter({
    sink: options.onCandles ? (candles) => options.onCandles?.(candles) : undefined,
  });
  const annotationRenderer = new ChartAnnotationRenderer(options.surface);
  const controller = new ChartController({ adapter, annotationRenderer });

  return {
    setSymbol: (symbol) => controller.setSymbol(symbol),
    setTimeframe: (tf) => controller.setTimeframe(tf),
    applyCandles: (candles: NormalizedCandle[]) => controller.applyCandles(candles),
    applyCandlePatch: (candle) => controller.applyCandlePatch(candle),
    applyAnnotations: (annotations: SemanticAnnotation[]) =>
      controller.applyAnnotations(annotations),
    destroy: () => controller.destroy(),
  };
}

/** Convenience for the live app: wire the engine to a TradingView widget. */
export function createTradingViewChartEngine(shapes: TradingViewShapeApi): ChartEngine {
  return createChartEngine({ surface: new TradingViewAnnotationSurface({ shapes }) });
}

export { ChartAnnotationRenderer } from "./ChartAnnotationRenderer";
export { ChartCandleAdapter } from "./ChartCandleAdapter";
export { ChartController } from "./ChartController";
export * from "./ChartDataAdapter";
export * from "./ChartTimeframeManager";
export * from "./ChartTypes";
export * from "./TradingViewAdapter";
