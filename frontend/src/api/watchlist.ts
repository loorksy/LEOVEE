import { apiFetch } from "@/api/httpClient";
import type { WatchlistListResponse } from "@/features/watchlist/types";

/** List watchlists + symbols; `with_quotes` embeds last H1 close per symbol (phase 29). */
export async function listWatchlists(withQuotes = false): Promise<WatchlistListResponse> {
  return apiFetch<WatchlistListResponse>("/api/v1/watchlists", {
    query: { with_quotes: withQuotes },
  });
}

export async function createWatchlist(name: string): Promise<{ id: string }> {
  return apiFetch<{ id: string }>("/api/v1/watchlists", {
    method: "POST",
    body: { name },
  });
}

export async function deleteWatchlist(id: string): Promise<void> {
  await apiFetch<void>(`/api/v1/watchlists/${id}`, { method: "DELETE" });
}

export async function addWatchlistSymbol(
  watchlistId: string,
  symbol: string,
): Promise<{ id: string }> {
  return apiFetch<{ id: string }>(`/api/v1/watchlists/${watchlistId}/symbols`, {
    method: "POST",
    body: { symbol },
  });
}
