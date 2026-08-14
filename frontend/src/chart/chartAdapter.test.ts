import { describe, expect, it } from "vitest";

import { dedupeCandles, mergeCandleUpdate, normalizeBackendCandle } from "./ChartDataAdapter";
import { ChartCandleAdapter } from "./ChartCandleAdapter";
import { resolveTimeframe } from "./ChartTimeframeManager";

describe("ChartDataAdapter", () => {
  it("normalizes backend candles to timestamp OHLC", () => {
    const candle = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
      complete: true,
    });
    expect(candle.timestamp).toBeGreaterThan(0);
    expect(candle.close).toBe(1.5);
    expect(candle.complete).toBe(true);
  });

  it("mergeCandleUpdate classifies tick vs new candle", () => {
    const base = [
      normalizeBackendCandle({
        ts: "2024-01-01T12:00:00.000Z",
        open: 1,
        high: 2,
        low: 0.5,
        close: 1.5,
      }),
    ];
    const tick = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.55,
      complete: false,
    });
    const { kind } = mergeCandleUpdate(base, tick);
    expect(kind).toBe("PRICE_UPDATED");

    const next = normalizeBackendCandle({
      ts: "2024-01-01T13:00:00.000Z",
      open: 1.55,
      high: 1.6,
      low: 1.5,
      close: 1.58,
    });
    const newer = mergeCandleUpdate(base, next);
    expect(newer.kind).toBe("NEW_CANDLE");
  });

  it("dedupeCandles keeps latest per timestamp", () => {
    const a = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.1,
    });
    const b = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.2,
    });
    const out = dedupeCandles([a, b]);
    expect(out).toHaveLength(1);
    expect(out[0].close).toBe(1.2);
  });
});

describe("ChartCandleAdapter", () => {
  it("switches timeframe without losing the candle series", () => {
    const adapter = new ChartCandleAdapter();
    adapter.setTimeframe("1H");
    const candle = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
    });
    adapter.applyCandles([candle]);
    // The chart's own spelling — `15M`, not the backend's `M15`.
    const { timeframe, changed } = resolveTimeframe("1H", "15M");
    expect(changed).toBe(true);
    adapter.setTimeframe(timeframe);

    expect(adapter.applyCandlePatch(candle)).toBe("CANDLE_UPDATED");
    expect(adapter.getCandles()).toHaveLength(1);
  });

  it("classifies a patch by where it lands in the series", () => {
    // The three kinds are different events: a new bar, the current bar moving,
    // and a correction to history. Collapsing them would make a late tick look
    // like the market having printed a new candle.
    const adapter = new ChartCandleAdapter();
    const at = (ts: string, close: number) =>
      normalizeBackendCandle({ ts, open: 1, high: 2, low: 0.5, close });

    adapter.applyCandles([at("2024-01-01T12:00:00.000Z", 1.5)]);
    expect(adapter.applyCandlePatch(at("2024-01-01T12:15:00.000Z", 1.6))).toBe("NEW_CANDLE");
    expect(adapter.applyCandlePatch(at("2024-01-01T12:15:00.000Z", 1.7))).toBe("CANDLE_UPDATED");
    expect(adapter.applyCandlePatch(at("2024-01-01T12:00:00.000Z", 1.4))).toBe("PRICE_UPDATED");
    expect(adapter.getCandles()).toHaveLength(2);
  });
});
