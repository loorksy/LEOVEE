import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChartStream } from "./useChartStream";
import { clearTokens, setTokens } from "@/api/authStore";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((event: { data: string }) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

describe("useChartStream", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    setTokens({ access_token: "tok", refresh_token: "r" });
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    clearTokens();
    vi.unstubAllGlobals();
  });

  it("does not connect until a workspaceId is available", () => {
    renderHook(() =>
      useChartStream({
        symbol: "XAUUSD",
        workspaceId: undefined,
        onCandle: vi.fn(),
        onAnnotationEvent: vi.fn(),
      }),
    );
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("connects with symbol + channels once workspaceId resolves and dispatches events", () => {
    const onCandle = vi.fn();
    const onAnnotationEvent = vi.fn();
    const { unmount } = renderHook(() =>
      useChartStream({ symbol: "XAUUSD", workspaceId: "ws-1", onCandle, onAnnotationEvent }),
    );

    expect(FakeWebSocket.instances).toHaveLength(1);
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toContain("symbols=XAUUSD");
    expect(socket.url).toContain("channels=candles%2Cannotations");
    expect(socket.url).toContain("workspace_id=ws-1");

    socket.onmessage?.({
      data: JSON.stringify({ ts: "2024-01-01T00:00:00.000Z", open: 1, high: 2, low: 0.5, close: 1.5 }),
    });
    expect(onCandle).toHaveBeenCalledTimes(1);

    socket.onmessage?.({
      data: JSON.stringify({
        event: "annotation_created",
        annotation: {
          id: "a",
          semantic_type: "DRAW_LEVEL",
          geometry: { anchors: [{ ts: "2024-01-01T00:00:00.000Z", price: 1.1 }] },
          status: "ACTIVE",
          version: 1,
        },
      }),
    });
    expect(onAnnotationEvent).toHaveBeenCalledTimes(1);

    unmount();
    expect(socket.closed).toBe(true);
  });

  it("ignores malformed frames without throwing", () => {
    const onCandle = vi.fn();
    const onAnnotationEvent = vi.fn();
    renderHook(() =>
      useChartStream({ symbol: "XAUUSD", workspaceId: "ws-1", onCandle, onAnnotationEvent }),
    );
    const socket = FakeWebSocket.instances[0];
    expect(() => socket.onmessage?.({ data: "not-json" })).not.toThrow();
    expect(onCandle).not.toHaveBeenCalled();
    expect(onAnnotationEvent).not.toHaveBeenCalled();
  });
});
