import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TradesPage } from "./TradesPage";

const listTrades = vi.fn();
const createTradeIdea = vi.fn();
vi.mock("../../api/trades", () => ({
  listTrades: (...args: unknown[]) => listTrades(...args),
  createTradeIdea: (...args: unknown[]) => createTradeIdea(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TradesPage />
    </QueryClientProvider>,
  );
}

describe("TradesPage", () => {
  beforeEach(() => {
    listTrades.mockReset();
    createTradeIdea.mockReset();
    listTrades.mockResolvedValue({
      items: [
        {
          id: "t1",
          symbol: "EURUSD",
          direction: "BUY",
          status: "IDEA",
        },
      ],
    });
  });

  it("lists trade ideas", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("trade-t1")).toBeInTheDocument());
    expect(screen.getByText(/Trade ideas only/i)).toBeInTheDocument();
    expect(screen.getByText(/OANDA_EXECUTION/i)).toBeInTheDocument();
  });
});
