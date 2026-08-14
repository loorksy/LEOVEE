import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";
import { TradesPage } from "./TradesPage";

const listTrades = vi.fn();
const createTradeIdea = vi.fn();
vi.mock("../../api/trades", () => ({
  listTrades: (...args: unknown[]) => listTrades(...args),
  createTradeIdea: (...args: unknown[]) => createTradeIdea(...args),
}));

describe("TradesPage", () => {
  beforeEach(() => {
    listTrades.mockReset();
    createTradeIdea.mockReset();
    listTrades.mockResolvedValue({
      items: [
        {
          id: "t1",
          symbol: "XAUUSD",
          direction: "BUY",
          status: "IDEA",
        },
      ],
    });
  });

  it("lists trade ideas", async () => {
    renderWithProviders(<TradesPage />);
    await waitFor(() => expect(screen.getByTestId("trade-t1")).toBeInTheDocument());
    expect(screen.getByTestId("trades-intro")).toBeInTheDocument();
  });
});
