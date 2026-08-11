import { useEffect, useRef } from "react";
import { buildAuthenticatedStreamUrl } from "@/api/realtime";
import { isCandleEvent, type CandleStreamEvent } from "@/features/chart/annotationStream";

export type UseWatchlistQuotesStreamOptions = {
  symbols: string[];
  enabled?: boolean;
  onQuote: (event: CandleStreamEvent) => void;
};

/**
 * Subscribes to `/ws/v1/stream?channels=candles` for every watchlist symbol.
 * Live OANDA ticks are published on this channel with `channel: "watchlist"`
 * (see `stream_consumer.py::_persist_live_candle`), so last-price columns
 * update incrementally without re-polling `with_quotes=true` (phase 29).
 */
export function useWatchlistQuotesStream(options: UseWatchlistQuotesStreamOptions): void {
  const { symbols, enabled = true, onQuote } = options;
  const onQuoteRef = useRef(onQuote);
  onQuoteRef.current = onQuote;

  const symbolsKey = symbols
    .slice()
    .sort()
    .join(",");

  useEffect(() => {
    if (!enabled || symbols.length === 0) return undefined;
    const url = buildAuthenticatedStreamUrl({ symbols, channels: ["candles"] });
    if (!url) return undefined;

    const socket = new WebSocket(url);
    socket.onmessage = (event: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (isCandleEvent(payload)) {
        onQuoteRef.current(payload);
      }
    };

    return () => {
      socket.close();
    };
    // symbols intentionally tracked via symbolsKey to avoid resubscribing on
    // referentially-new-but-equal arrays.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, symbolsKey]);
}
