import type { KLineChartLike, NormalizedCandle } from "./ChartTypes";
import { toKLineData } from "./ChartDataAdapter";

export type KLineChartAdapterOptions = {
  chart: KLineChartLike;
};

export class KLineChartAdapter {
  private readonly chart: KLineChartLike;
  private symbol = "EURUSD";
  private timeframe = "1H";
  private candles: NormalizedCandle[] = [];

  constructor(options: KLineChartAdapterOptions) {
    this.chart = options.chart;
  }

  setSymbol(symbol: string): void {
    this.symbol = symbol.toUpperCase();
  }

  getSymbol(): string {
    return this.symbol;
  }

  setTimeframe(timeframe: string): void {
    this.timeframe = timeframe.toUpperCase();
  }

  getTimeframe(): string {
    return this.timeframe;
  }

  applyCandles(candles: NormalizedCandle[]): void {
    this.candles = candles;
    this.chart.applyNewData(candles.map(toKLineData));
  }

  applyCandlePatch(candle: NormalizedCandle): void {
    const last = this.candles[this.candles.length - 1];
    if (!last || candle.timestamp > last.timestamp) {
      this.candles = [...this.candles, candle];
      this.chart.applyNewData(this.candles.map(toKLineData));
      return;
    }
    if (candle.timestamp === last.timestamp) {
      this.candles = [...this.candles.slice(0, -1), { ...last, ...candle }];
      this.chart.updateData(toKLineData(this.candles[this.candles.length - 1]));
      return;
    }
    this.chart.updateData(toKLineData(candle));
  }

  getCandles(): NormalizedCandle[] {
    return this.candles;
  }
}
