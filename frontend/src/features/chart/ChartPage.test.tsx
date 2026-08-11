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

describe("ChartPage", () => {
  it("loads candles + annotations and feeds them into the chart engine", async () => {
    vi.spyOn(marketsApi, "getCandles").mockResolvedValue({
      symbol: "EURUSD",
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
          semantic_type: "DRAW_LEVEL",
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
    expect(await screen.findByText(/1 annotation\(s\) loaded/)).toBeInTheDocument();
  });
});
