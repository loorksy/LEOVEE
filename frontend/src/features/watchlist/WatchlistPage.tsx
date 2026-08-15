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
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { Trash2 } from "lucide-react";

const QUOTE_POLL_MS = 15_000;

export function WatchlistPage() {
  const { t } = useLocale();
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
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="watchlist-title"
        title={t("watchlist.title")}
        description={t("watchlist.intro")}
      />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (newListName.trim()) createMutation.mutate(newListName.trim());
        }}
        className="flex flex-col gap-2 sm:flex-row"
      >
        <label htmlFor="new-watchlist-name" className="sr-only">
          {t("watchlist.newName")}
        </label>
        <Input
          id="new-watchlist-name"
          data-testid="new-watchlist-name"
          value={newListName}
          onChange={(event) => setNewListName(event.target.value)}
          placeholder={t("watchlist.newName")}
          className="sm:w-64"
        />
        <Button type="submit" data-testid="create-watchlist" disabled={createMutation.isPending}>
          {t("watchlist.create")}
        </Button>
      </form>

      {watchlistsQuery.isLoading && (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="watchlist-loading"
        >
          {Array.from({ length: 2 }).map((_, index) => (
            <Card key={index} className="flex flex-col gap-3 p-3">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </Card>
          ))}
        </div>
      )}
      {watchlistsQuery.isError && (
        <p className="text-sm text-destructive">{t("common.error.load")}</p>
      )}
      {!watchlistsQuery.isLoading && items.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="watchlist-empty">
          {t("watchlist.empty")}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((wl) => (
          <Card key={wl.id} data-testid={`watchlist-${wl.id}`} className="flex flex-col">
            <CardHeader className="flex-row items-center justify-between gap-2">
              <CardTitle className="min-w-0 truncate text-base">{wl.name}</CardTitle>
              <IconButton
                aria-label={t("common.delete")}
                data-testid={`delete-watchlist-${wl.id}`}
                onClick={() => deleteMutation.mutate(wl.id)}
                disabled={deleteMutation.isPending}
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 className="size-4" aria-hidden="true" />
              </IconButton>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
              <ul className="flex flex-col gap-1 text-sm">
                {wl.symbols.map((sym) => {
                  const price = liveQuotes[sym.code] ?? sym.last_price;
                  return (
                    <li
                      key={sym.item_id}
                      className="flex items-center justify-between gap-2 text-muted-foreground"
                    >
                      <span className="font-mono">{sym.code}</span>
                      <span data-testid={`quote-${sym.code}`} className="font-mono text-foreground">
                        {price ?? "—"}
                      </span>
                    </li>
                  );
                })}
                {wl.symbols.length === 0 && (
                  <li className="text-muted-foreground">{t("watchlist.noSymbols")}</li>
                )}
              </ul>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const symbol = symbolDrafts[wl.id]?.trim();
                  if (symbol) addSymbolMutation.mutate({ watchlistId: wl.id, symbol });
                }}
                className="mt-auto flex flex-col gap-2 sm:flex-row"
              >
                <label htmlFor={`symbol-${wl.id}`} className="sr-only">
                  {t("watchlist.addSymbol")}
                </label>
                <Input
                  id={`symbol-${wl.id}`}
                  value={symbolDrafts[wl.id] ?? ""}
                  onChange={(event) =>
                    setSymbolDrafts((prev) => ({
                      ...prev,
                      [wl.id]: event.target.value.toUpperCase(),
                    }))
                  }
                  placeholder={DEFAULT_SYMBOL}
                  className="sm:w-32"
                />
                <Button
                  type="submit"
                  variant="outline"
                  size="sm"
                  disabled={addSymbolMutation.isPending}
                >
                  {t("watchlist.add")}
                </Button>
              </form>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
