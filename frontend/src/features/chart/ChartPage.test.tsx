import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { ChartPage } from "./ChartPage";
import * as marketsApi from "@/api/markets";
import * as chartApi from "@/api/chart";
import * as workspaceHook from "@/hooks/useWorkspaceId";
import * as chartStreamHook from "@/features/chart/useChartStream";

const fakeEngine = {
  setSymbol: vi.fn(),
  setTimeframe: vi.fn(),
  applyCandles: vi.fn(),
  applyCandlePatch: vi.fn(),
  applyAnnotations: vi.fn(),
  destroy: vi.fn(),
};

vi.mock("@/chart", async () => {
  const actual = await vi.importActual<typeof import("@/chart")>("@/chart");
  return {
    ...actual,
    createChartEngine: vi.fn(() => fakeEngine),
  };
});

// The real component loads 27 MB of vendored charting library from a script
// tag. Stubbed so the page can be tested at all — and stubbed to *call back*
// immediately, because the engine is now created when the chart hands over its
// drawing surface. A stub that rendered nothing would leave no engine, and the
// test would pass by asserting against a page that never got one.
vi.mock("@/chart/tradingview/TradingViewChart", () => ({
  TradingViewChart: ({
    onShapesReady,
  }: {
    onShapesReady: (shapes: unknown) => void;
  }) => {
    onShapesReady({ createMultipointShape: vi.fn(() => "shape-1"), removeEntity: vi.fn() });
    return <div data-testid="tradingview-chart" />;
  },
}));

describe("ChartPage", () => {
  it("loads candles + annotations and feeds them into the chart engine", async () => {
    vi.spyOn(marketsApi, "getCandles").mockResolvedValue({
      symbol: "XAUUSD",
      timeframe: "H1",
      workspace_id: "ws-1",
      candles: [
        { ts: "2024-01-01T00:00:00.000Z", open: 1, high: 1.1, low: 0.9, close: 1.05 },
      ],
    });
    vi.spyOn(chartApi, "listChartAnnotations").mockResolvedValue({
      items: [
        {
          id: "ann-1",
          semantic_type: "price_line",
          geometry: { anchors: [{ ts: "2024-01-01T00:00:00.000Z", price: 1.05 }] },
          status: "ACTIVE",
          version: 1,
        },
      ],
    });
    vi.spyOn(workspaceHook, "useWorkspaceId").mockReturnValue({
      data: "ws-1",
    } as ReturnType<typeof workspaceHook.useWorkspaceId>);
    vi.spyOn(chartStreamHook, "useChartStream").mockImplementation(() => undefined);

    renderWithProviders(<ChartPage />);

    expect(screen.getByTestId("chart-container")).toBeInTheDocument();

    await waitFor(() => expect(fakeEngine.applyCandles).toHaveBeenCalled());
    await waitFor(() => expect(fakeEngine.applyAnnotations).toHaveBeenCalled());
    expect(await screen.findByTestId("annotation-count")).toBeInTheDocument();
  });
});
