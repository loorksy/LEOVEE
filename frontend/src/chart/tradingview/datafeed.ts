/**
 * The library's data source, backed by Leovee's own candle API.
 *
 * **Read-only, and gold-only (D10).** The symbol search returns exactly one
 * instrument because there is exactly one; a search box that offers others
 * would promise a market the platform cannot analyse.
 *
 * **Library indicators are display-only.** This feeds bars and nothing else.
 * Any number the agent reasons about arrives through the analysis API, computed
 * by the Python engines — letting the client re-derive one is how the chart and
 * the narrative come to disagree by a rounding step.
 */

import type { NormalizedCandle } from "../ChartTypes";

export type DatafeedBar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type LoadCandles = (
  symbol: string,
  resolution: string,
  from: number,
  to: number,
) => Promise<NormalizedCandle[]>;

/** The library's resolution strings, mapped to the backend's frame codes. */
const RESOLUTION_TO_TIMEFRAME: Record<string, string> = {
  "1": "M1",
  "5": "M5",
  "15": "M15",
  "60": "H1",
  "240": "H4",
};

export function timeframeForResolution(resolution: string): string {
  return RESOLUTION_TO_TIMEFRAME[resolution] ?? "M15";
}

/** The inverse, derived from the same table so the two cannot disagree. */
export function resolutionForTimeframe(timeframe: string): string {
  const wanted = timeframe.toUpperCase();
  const found = Object.entries(RESOLUTION_TO_TIMEFRAME).find(([, code]) => code === wanted);
  return found ? found[0] : "15";
}

export function toDatafeedBar(candle: NormalizedCandle): DatafeedBar {
  return {
    // The library's bar time is in **milliseconds**, unlike its shape-point
    // time, which is in seconds. Getting this backwards puts every bar in the
    // wrong millennium, and the chart renders it without complaint.
    time: candle.timestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
  };
}

export const GOLD_SYMBOL_INFO = {
  name: "XAUUSD",
  ticker: "XAUUSD",
  description: "Gold / US Dollar",
  type: "commodity",
  session: "24x7",
  timezone: "Etc/UTC",
  // Gold prices to two decimals. `pricescale: 10000` — the currency-pair
  // convention — draws every level a hundred times too finely and makes the
  // price axis unreadable.
  pricescale: 100,
  minmov: 1,
  has_intraday: true,
  supported_resolutions: Object.keys(RESOLUTION_TO_TIMEFRAME),
  volume_precision: 0,
  data_status: "streaming",
};

export function createDatafeed(loadCandles: LoadCandles): Record<string, unknown> {
  return {
    onReady: (callback: (config: unknown) => void) => {
      setTimeout(
        () =>
          callback({
            supported_resolutions: GOLD_SYMBOL_INFO.supported_resolutions,
            supports_marks: false,
            supports_timescale_marks: false,
            supports_time: true,
          }),
        0,
      );
    },
    searchSymbols: (
      _input: string,
      _exchange: string,
      _type: string,
      onResult: (items: unknown[]) => void,
    ) => {
      onResult([GOLD_SYMBOL_INFO]);
    },
    resolveSymbol: (
      _name: string,
      onResolve: (info: unknown) => void,
    ) => {
      setTimeout(() => onResolve(GOLD_SYMBOL_INFO), 0);
    },
    getBars: async (
      symbolInfo: { name: string },
      resolution: string,
      periodParams: { from: number; to: number; firstDataRequest: boolean },
      onResult: (bars: DatafeedBar[], meta: { noData: boolean }) => void,
      onError: (reason: string) => void,
    ) => {
      try {
        const candles = await loadCandles(
          symbolInfo.name,
          resolution,
          periodParams.from,
          periodParams.to,
        );
        const bars = candles.map(toDatafeedBar);
        // `noData: true` is how the library learns to stop paging backwards.
        // Omitting it makes it request older history forever.
        onResult(bars, { noData: bars.length === 0 });
      } catch (error) {
        onError(error instanceof Error ? error.message : String(error));
      }
    },
    subscribeBars: () => {
      // Live updates arrive over the existing SSE stream and are pushed in
      // through `ChartEngine.applyCandlePatch`. A second subscription here
      // would poll the same data on its own schedule and the two would
      // disagree about which bar is current.
    },
    unsubscribeBars: () => {},
  };
}
