import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addWatchlistSymbol,
  createWatchlist,
  deleteWatchlist,
  listWatchlists,
} from "@/api/watchlist";
import { useWatchlistQuotesStream } from "@/features/watchlist/useWatchlistQuotesStream";

const QUOTE_POLL_MS = 15_000;

export function WatchlistPage() {
  const queryClient = useQueryClient();
  const [newListName, setNewListName] = useState("");
  const [symbolDrafts, setSymbolDrafts] = useState<Record<string, string>>({});
  const [liveQuotes, setLiveQuotes] = useState<Record<string, number>>({});

  const watchlistsQuery = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => listWatchlists(true),
    refetchInterval: QUOTE_POLL_MS,
  });

  const wsSymbols = watchlistsQuery.data?.ws_symbols ?? [];

  useWatchlistQuotesStream({
    symbols: wsSymbols,
    onQuote: (candle) => {
      if (!candle.symbol) return;
      setLiveQuotes((prev) => ({ ...prev, [candle.symbol as string]: candle.close }));
    },
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createWatchlist(name),
    onSuccess: async () => {
      setNewListName("");
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteWatchlist(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  const addSymbolMutation = useMutation({
    mutationFn: ({ watchlistId, symbol }: { watchlistId: string; symbol: string }) =>
      addWatchlistSymbol(watchlistId, symbol),
    onSuccess: async (_result, variables) => {
      setSymbolDrafts((prev) => ({ ...prev, [variables.watchlistId]: "" }));
      await queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  const items = watchlistsQuery.data?.items ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Watchlist</h1>
        <p className="mt-1 text-slate-400">
          Track symbols across your workspace — quotes refresh via polling
          (<code>with_quotes=true</code>) and live <code>/ws/v1/stream?channels=candles</code>{" "}
          ticks (§29).
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (newListName.trim()) createMutation.mutate(newListName.trim());
        }}
        className="flex gap-2"
      >
        <label htmlFor="new-watchlist-name" className="sr-only">
          New watchlist name
        </label>
        <input
          id="new-watchlist-name"
          value={newListName}
          onChange={(event) => setNewListName(event.target.value)}
          placeholder="New watchlist name"
          className="w-64 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
        />
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          Create watchlist
        </button>
      </form>

      {watchlistsQuery.isLoading && <p className="text-slate-400">Loading watchlists…</p>}
      {watchlistsQuery.isError && <p className="text-amber-400">Could not load watchlists.</p>}
      {!watchlistsQuery.isLoading && items.length === 0 && (
        <p className="text-slate-400">No watchlists yet — create one above.</p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {items.map((wl) => (
          <section
            key={wl.id}
            data-testid={`watchlist-${wl.id}`}
            className="rounded-lg border border-slate-800 bg-leovee-panel p-4"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-100">{wl.name}</h2>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(wl.id)}
                className="text-sm text-red-400 hover:text-red-300"
              >
                Delete
              </button>
            </div>
            <ul className="mt-3 space-y-1 text-sm">
              {wl.symbols.map((sym) => {
                const price = liveQuotes[sym.code] ?? sym.last_price;
                return (
                  <li key={sym.item_id} className="flex justify-between text-slate-300">
                    <span>{sym.code}</span>
                    <span data-testid={`quote-${sym.code}`} className="text-slate-100">
                      {price ?? "—"}
                    </span>
                  </li>
                );
              })}
              {wl.symbols.length === 0 && <li className="text-slate-500">No symbols yet.</li>}
            </ul>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const symbol = symbolDrafts[wl.id]?.trim();
                if (symbol) addSymbolMutation.mutate({ watchlistId: wl.id, symbol });
              }}
              className="mt-3 flex gap-2"
            >
              <label htmlFor={`symbol-${wl.id}`} className="sr-only">
                Add symbol to {wl.name}
              </label>
              <input
                id={`symbol-${wl.id}`}
                value={symbolDrafts[wl.id] ?? ""}
                onChange={(event) =>
                  setSymbolDrafts((prev) => ({
                    ...prev,
                    [wl.id]: event.target.value.toUpperCase(),
                  }))
                }
                placeholder={DEFAULT_SYMBOL}
                className="w-32 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
              />
              <button
                type="submit"
                disabled={addSymbolMutation.isPending}
                className="rounded border border-slate-700 px-3 py-1 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                Add
              </button>
            </form>
          </section>
        ))}
      </div>
    </div>
  );
}
