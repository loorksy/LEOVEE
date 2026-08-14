import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createTradeIdea, listTrades } from "@/api/trades";
import { useLocale } from "@/i18n/context";

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

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">{t("trades.title")}</h1>
        <p className="text-sm text-slate-400" data-testid="trades-intro">
          {t("trades.intro")}
        </p>
      </header>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          createMutation.mutate();
        }}
      >
        <label className="text-xs text-slate-400">
          {t("common.symbol")}
          <input
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          />
        </label>
        <label className="text-xs text-slate-400">
          {t("trades.direction")}
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
            value={direction}
            onChange={(e) => setDirection(e.target.value as "BUY" | "SELL")}
          >
            <option value="BUY">{t("direction.buy")}</option>
            <option value="SELL">{t("direction.sell")}</option>
          </select>
        </label>
        <button
          type="submit"
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white"
          disabled={createMutation.isPending}
        >
          {t("trades.create")}
        </button>
      </form>
      {createMutation.isError && (
        <p className="text-sm text-amber-400">{(createMutation.error as Error).message}</p>
      )}
      <ul className="space-y-2 text-sm text-slate-300">
        {(tradesQuery.data?.items ?? []).map((trade) => (
          <li
            key={trade.id}
            className="rounded border border-slate-800 bg-leovee-panel px-4 py-3"
            data-testid={`trade-${trade.id}`}
          >
            <span className="font-medium text-slate-100">
              {trade.symbol ?? "—"}{" "}
              {trade.direction === "BUY" ? t("direction.buy") : t("direction.sell")}
            </span>
            {trade.status ? <span className="ms-2 text-slate-500">{trade.status}</span> : null}
          </li>
        ))}
      </ul>
      {!tradesQuery.isLoading && (tradesQuery.data?.items.length ?? 0) === 0 && (
        <p className="text-slate-400" data-testid="trades-empty">
          {t("trades.empty")}
        </p>
      )}
    </div>
  );
}
