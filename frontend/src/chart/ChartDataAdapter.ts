import type { CandleUpdateKind, NormalizedCandle } from "./ChartTypes";

export type BackendCandlePayload = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  complete?: boolean;
};

export function parseTimestamp(ts: string): number {
  return new Date(ts).getTime();
}

export function normalizeBackendCandle(raw: BackendCandlePayload): NormalizedCandle {
  return {
    timestamp: parseTimestamp(raw.ts),
    open: raw.open,
    high: raw.high,
    low: raw.low,
    close: raw.close,
    volume: raw.volume ?? 0,
    complete: raw.complete ?? true,
  };
}

export function toKLineData(candle: NormalizedCandle): {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
} {
  return {
    timestamp: candle.timestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
  };
}

export function mergeCandleUpdate(
  series: NormalizedCandle[],
  patch: NormalizedCandle,
): { series: NormalizedCandle[]; kind: CandleUpdateKind } {
  if (series.length === 0) {
    return { series: [patch], kind: "NEW_CANDLE" };
  }
  const last = series[series.length - 1];
  if (patch.timestamp > last.timestamp) {
    return { series: [...series, patch], kind: "NEW_CANDLE" };
  }
  if (patch.timestamp === last.timestamp) {
    const updated = { ...last, ...patch };
    const next = [...series.slice(0, -1), updated];
    if (patch.complete === false && patch.close !== last.close) {
      return { series: next, kind: "PRICE_UPDATED" };
    }
    return { series: next, kind: "CANDLE_UPDATED" };
  }
  const idx = series.findIndex((c) => c.timestamp === patch.timestamp);
  if (idx >= 0) {
    const next = [...series];
    next[idx] = { ...next[idx], ...patch };
    return { series: next, kind: "CANDLE_UPDATED" };
  }
  return { series: [...series, patch], kind: "NEW_CANDLE" };
}

export function dedupeCandles(candles: NormalizedCandle[]): NormalizedCandle[] {
  const byTs = new Map<number, NormalizedCandle>();
  for (const candle of candles) {
    byTs.set(candle.timestamp, candle);
  }
  return [...byTs.values()].sort((a, b) => a.timestamp - b.timestamp);
}
