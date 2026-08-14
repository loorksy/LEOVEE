import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { WatchlistPage } from "./WatchlistPage";
import * as watchlistApi from "@/api/watchlist";
import * as watchlistStreamHook from "@/features/watchlist/useWatchlistQuotesStream";

describe("WatchlistPage", () => {
  it("lists watchlists with symbols and quotes from with_quotes=true", async () => {
    vi.spyOn(watchlistApi, "listWatchlists").mockResolvedValue({
      items: [
        {
          id: "wl-1",
          name: "Majors",
          symbols: [{ code: "XAUUSD", item_id: "item-1", last_price: 1.0812 }],
        },
      ],
      ws_symbols: ["XAUUSD"],
    });
    vi.spyOn(watchlistStreamHook, "useWatchlistQuotesStream").mockImplementation(() => undefined);

    renderWithProviders(<WatchlistPage />);

    expect(await screen.findByText("Majors")).toBeInTheDocument();
    expect(screen.getByText("XAUUSD")).toBeInTheDocument();
    expect(await screen.findByTestId("quote-XAUUSD")).toHaveTextContent("1.0812");
    expect(watchlistApi.listWatchlists).toHaveBeenCalledWith(true);
  });

  it("creates a watchlist from the form", async () => {
    vi.spyOn(watchlistApi, "listWatchlists").mockResolvedValue({ items: [], ws_symbols: [] });
    vi.spyOn(watchlistStreamHook, "useWatchlistQuotesStream").mockImplementation(() => undefined);
    const createSpy = vi.spyOn(watchlistApi, "createWatchlist").mockResolvedValue({ id: "wl-2" });

    renderWithProviders(<WatchlistPage />);

    expect(await screen.findByTestId("watchlist-empty")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("new-watchlist-name"), {
      target: { value: "Metals" },
    });
    fireEvent.click(screen.getByTestId("create-watchlist"));

    await waitFor(() => expect(createSpy).toHaveBeenCalledWith("Metals"));
  });
});
