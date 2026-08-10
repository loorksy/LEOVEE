import { useEffect, useRef } from "react";
import { buildAuthenticatedStreamUrl } from "@/api/realtime";
import {
  isAnnotationEvent,
  isCandleEvent,
  type AnnotationStreamEvent,
  type CandleStreamEvent,
} from "@/features/chart/annotationStream";

export type UseChartStreamOptions = {
  symbol: string;
  workspaceId: string | null | undefined;
  enabled?: boolean;
  onCandle: (candle: CandleStreamEvent) => void;
  onAnnotationEvent: (event: AnnotationStreamEvent) => void;
};

/**
 * Subscribes to `/ws/v1/stream?channels=candles,annotations` for a symbol +
 * workspace, dispatching incremental candle/annotation updates (§25 — no full
 * rebuild on tick).
 */
export function useChartStream(options: UseChartStreamOptions): void {
  const { symbol, workspaceId, enabled = true, onCandle, onAnnotationEvent } = options;
  const onCandleRef = useRef(onCandle);
  const onAnnotationRef = useRef(onAnnotationEvent);
  onCandleRef.current = onCandle;
  onAnnotationRef.current = onAnnotationEvent;

  useEffect(() => {
    if (!enabled || !workspaceId) return;
    const url = buildAuthenticatedStreamUrl({
      symbols: [symbol],
      channels: ["candles", "annotations"],
      workspaceId,
    });
    if (!url) return;

    const socket = new WebSocket(url);
    socket.onmessage = (event: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (isAnnotationEvent(payload)) {
        onAnnotationRef.current(payload);
        return;
      }
      if (isCandleEvent(payload)) {
        onCandleRef.current(payload);
      }
    };

    return () => {
      socket.close();
    };
  }, [enabled, symbol, workspaceId]);
}
