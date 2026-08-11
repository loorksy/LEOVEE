import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarketsPage } from "./MarketsPage";

const getCandles = vi.fn();
vi.mock("../../api/markets", () => ({
  getCandles: (...args: unknown[]) => getCandles(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketsPage />
    </QueryClientProvider>,
  );
}

describe("MarketsPage", () => {
  beforeEach(() => {
    getCandles.mockReset();
    getCandles.mockResolvedValue({
      symbol: "EURUSD",
      timeframe: "H1",
      workspace_id: "w1",
      candles: [
        {
          ts: "2026-01-01T00:00:00.000Z",
          open: 1.1,
          high: 1.11,
          low: 1.09,
          close: 1.105,
        },
      ],
    });
  });

  it("lists candles from markets API", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("1.105")).toBeInTheDocument());
    expect(getCandles).toHaveBeenCalledWith("EURUSD", "H1", 50);
  });
});
