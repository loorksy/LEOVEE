/**
 * Candle state, independent of who draws it.
 *
 * This replaces `KLineChartAdapter`, which held the same state and pushed it
 * into a specific library on every change. Keeping the series here and letting
 * the surface subscribe is what makes the renderer replaceable: the controller
 * never learns which chart it is talking to.
 */

import type { CandleUpdateKind, NormalizedCandle } from "./ChartTypes";

export type CandleSink = (candles: NormalizedCandle[], kind: CandleUpdateKind | null) => void;

export class ChartCandleAdapter {
  private symbol = "XAUUSD";
  private timeframe = "M15";
  private candles: NormalizedCandle[] = [];
  private readonly sink: CandleSink | undefined;

  constructor(options: { sink?: CandleSink } = {}) {
    this.sink = options.sink;
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
    this.sink?.(this.candles, null);
  }

  applyCandlePatch(candle: NormalizedCandle): CandleUpdateKind {
    const last = this.candles[this.candles.length - 1];
    if (!last || candle.timestamp > last.timestamp) {
      this.candles = [...this.candles, candle];
      this.sink?.(this.candles, "NEW_CANDLE");
      return "NEW_CANDLE";
    }
    if (candle.timestamp === last.timestamp) {
      this.candles = [...this.candles.slice(0, -1), { ...last, ...candle }];
      this.sink?.(this.candles, "CANDLE_UPDATED");
      return "CANDLE_UPDATED";
    }
    // Older than the last bar: a correction to history, not a new print.
    this.candles = this.candles.map((existing) =>
      existing.timestamp === candle.timestamp ? { ...existing, ...candle } : existing,
    );
    this.sink?.(this.candles, "PRICE_UPDATED");
    return "PRICE_UPDATED";
  }

  getCandles(): NormalizedCandle[] {
    return this.candles;
  }
}
