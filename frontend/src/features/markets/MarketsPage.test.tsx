import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarketsPage } from "./MarketsPage";

const getCandles = vi.fn();
const getProvidersStatus = vi.fn();
vi.mock("../../api/markets", () => ({
  getCandles: (...args: unknown[]) => getCandles(...args),
}));
vi.mock("../../api/providers", () => ({
  getProvidersStatus: (...args: unknown[]) => getProvidersStatus(...args),
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
    getProvidersStatus.mockReset();
  });

  it("shows not-configured state when OANDA is missing", async () => {
    getProvidersStatus.mockResolvedValue({
      finnhub: { configured: false, status: "not_configured" },
      oanda: { configured: false, status: "not_configured", environment: "practice" },
      anthropic: { configured: true, status: "ok" },
      openai: { configured: true, status: "ok" },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("oanda-provider-not-configured")).toBeInTheDocument(),
    );
    expect(screen.getByText(/OANDA_API_TOKEN/)).toBeInTheDocument();
    expect(screen.getByText(/not an empty-data state/i)).toBeInTheDocument();
    expect(getCandles).not.toHaveBeenCalled();
  });

  it("lists candles when OANDA is configured", async () => {
    getProvidersStatus.mockResolvedValue({
      finnhub: { configured: false, status: "not_configured" },
      oanda: { configured: true, status: "ok", environment: "practice" },
      anthropic: { configured: true, status: "ok" },
      openai: { configured: true, status: "ok" },
    });
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
    renderPage();
    await waitFor(() => expect(screen.getByText("1.105")).toBeInTheDocument());
    expect(getCandles).toHaveBeenCalledWith("EURUSD", "H1", 50);
  });
});
