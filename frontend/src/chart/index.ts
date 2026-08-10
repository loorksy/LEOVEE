import { dispose, init, type Chart } from "klinecharts";

import type { ChartEngine, KLineChartLike, NormalizedCandle, SemanticAnnotation } from "./ChartTypes";
import { ChartAnnotationRenderer } from "./ChartAnnotationRenderer";
import { ChartController } from "./ChartController";
import { KLineChartAdapter } from "./KLineChartAdapter";

function asKLineChartLike(chart: Chart): KLineChartLike {
  return chart as unknown as KLineChartLike;
}

export type CreateChartEngineOptions = {
  container: HTMLElement;
};

export function createChartEngine(options: CreateChartEngineOptions): ChartEngine {
  const chart = init(options.container);
  if (!chart) {
    throw new Error("KLineChart failed to initialize");
  }
  const like = asKLineChartLike(chart);
  const adapter = new KLineChartAdapter({ chart: like });
  const annotationRenderer = new ChartAnnotationRenderer(like);
  const controller = new ChartController({ adapter, annotationRenderer });

  return {
    setSymbol: (symbol) => controller.setSymbol(symbol),
    setTimeframe: (tf) => controller.setTimeframe(tf),
    applyCandles: (candles: NormalizedCandle[]) => controller.applyCandles(candles),
    applyCandlePatch: (candle) => controller.applyCandlePatch(candle),
    applyAnnotations: (annotations: SemanticAnnotation[]) =>
      controller.applyAnnotations(annotations),
    destroy: () => {
      controller.destroy();
      dispose(chart);
    },
  };
}

export { ChartAnnotationRenderer } from "./ChartAnnotationRenderer";
export { ChartController } from "./ChartController";
export * from "./ChartDataAdapter";
export * from "./ChartTimeframeManager";
export * from "./ChartTypes";
export { KLineChartAdapter } from "./KLineChartAdapter";
