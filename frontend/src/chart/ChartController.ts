import type { ChartEngine, NormalizedCandle, SemanticAnnotation } from "./ChartTypes";
import { ChartAnnotationRenderer } from "./ChartAnnotationRenderer";
import {
  mergeCandleUpdate,
  type BackendCandlePayload,
  normalizeBackendCandle,
} from "./ChartDataAdapter";
import { KLineChartAdapter } from "./KLineChartAdapter";
import { resolveTimeframe } from "./ChartTimeframeManager";

export type ChartControllerOptions = {
  adapter: KLineChartAdapter;
  annotationRenderer: ChartAnnotationRenderer;
};

export class ChartController implements ChartEngine {
  private readonly adapter: KLineChartAdapter;
  private readonly annotationRenderer: ChartAnnotationRenderer;
  private candles: NormalizedCandle[] = [];
  private annotations: SemanticAnnotation[] = [];

  constructor(options: ChartControllerOptions) {
    this.adapter = options.adapter;
    this.annotationRenderer = options.annotationRenderer;
  }

  setSymbol(symbol: string): void {
    this.adapter.setSymbol(symbol);
  }

  setTimeframe(timeframe: string): void {
    const { timeframe: resolved, changed } = resolveTimeframe(
      this.adapter.getTimeframe(),
      timeframe,
    );
    if (changed) {
      this.adapter.setTimeframe(resolved);
      this.adapter.applyCandles(this.candles);
      this.annotationRenderer.applyIncremental(this.annotations);
    }
  }

  applyCandles(candles: NormalizedCandle[]): void {
    this.candles = candles;
    this.adapter.applyCandles(candles);
  }

  ingestBackendCandles(raw: BackendCandlePayload[]): void {
    this.applyCandles(raw.map(normalizeBackendCandle));
  }

  applyCandlePatch(candle: NormalizedCandle) {
    const { series, kind } = mergeCandleUpdate(this.candles, candle);
    this.candles = series;
    this.adapter.applyCandlePatch(candle);
    return kind;
  }

  applyAnnotations(annotations: SemanticAnnotation[]): void {
    this.annotations = annotations;
    this.annotationRenderer.applyIncremental(annotations);
  }

  destroy(): void {
    this.annotationRenderer.clear();
    this.candles = [];
    this.annotations = [];
  }
}
