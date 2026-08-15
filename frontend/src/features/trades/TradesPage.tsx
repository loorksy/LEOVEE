import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createTradeIdea, listTrades } from "@/api/trades";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";

export function TradesPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [direction, setDirection] = useState<"BUY" | "SELL">("BUY");
  const tradesQuery = useQuery({ queryKey: ["trades"], queryFn: listTrades });

  const createMutation = useMutation({
    mutationFn: () => createTradeIdea({ symbol, direction }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["trades"] });
    },
  });

  const trades = tradesQuery.data?.items ?? [];

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="trades-title"
        title={t("trades.title")}
        description={<span data-testid="trades-intro">{t("trades.intro")}</span>}
      />

      <form
        className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          createMutation.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="trade-symbol">
          {t("common.symbol")}
          <Input
            id="trade-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="sm:w-32"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="trade-direction">
          {t("trades.direction")}
          <select
            id="trade-direction"
            className="h-11 rounded-md border border-border bg-input px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background sm:h-9 sm:w-32"
            value={direction}
            onChange={(e) => setDirection(e.target.value as "BUY" | "SELL")}
          >
            <option value="BUY">{t("direction.buy")}</option>
            <option value="SELL">{t("direction.sell")}</option>
          </select>
        </label>
        <Button type="submit" disabled={createMutation.isPending}>
          {t("trades.create")}
        </Button>
      </form>
      {createMutation.isError && (
        <p className="text-sm text-destructive">{(createMutation.error as Error).message}</p>
      )}

      {tradesQuery.isLoading && (
        <div className="flex flex-col gap-2" data-testid="trades-loading">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}
      {tradesQuery.isError && <p className="text-sm text-destructive">{t("common.error.load")}</p>}

      <ul className="flex flex-col gap-2">
        {trades.map((trade) => (
          <li key={trade.id} data-testid={`trade-${trade.id}`}>
            <Card className="flex flex-wrap items-center justify-between gap-3 p-3">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate font-mono text-sm font-medium text-foreground">
                  {trade.symbol ?? "—"}
                </span>
                <Badge variant={trade.direction === "BUY" ? "buy" : "sell"}>
                  {trade.direction === "BUY" ? t("direction.buy") : t("direction.sell")}
                </Badge>
              </div>
              {trade.status ? <Badge variant="neutral">{trade.status}</Badge> : null}
            </Card>
          </li>
        ))}
      </ul>
      {!tradesQuery.isLoading && trades.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="trades-empty">
          {t("trades.empty")}
        </p>
      )}
    </div>
  );
}
