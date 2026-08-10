import { describe, expect, it, vi } from "vitest";

import { dedupeCandles, mergeCandleUpdate, normalizeBackendCandle, toKLineData } from "./ChartDataAdapter";
import { KLineChartAdapter } from "./KLineChartAdapter";
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
    expect(toKLineData(candle).close).toBe(1.5);
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

describe("KLineChartAdapter", () => {
  it("switches timeframe without losing candle series", () => {
    const chart = {
      applyNewData: vi.fn(),
      updateData: vi.fn(),
      createOverlay: vi.fn(),
      removeOverlay: vi.fn(),
    };
    const adapter = new KLineChartAdapter({ chart });
    adapter.setTimeframe("1H");
    const candle = normalizeBackendCandle({
      ts: "2024-01-01T12:00:00.000Z",
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
    });
    adapter.applyCandles([candle]);
    const { timeframe, changed } = resolveTimeframe("1H", "15M");
    expect(changed).toBe(true);
    adapter.setTimeframe(timeframe);
    adapter.applyCandlePatch(candle);
    expect(chart.updateData).toHaveBeenCalled();
    expect(adapter.getCandles()).toHaveLength(1);
  });
});
