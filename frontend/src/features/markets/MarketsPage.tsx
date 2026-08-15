import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useQuery } from "@tanstack/react-query";
import { getCandles } from "@/api/markets";
import { getProvidersStatus } from "@/api/providers";
import { ProviderNotConfiguredBanner } from "@/components/ProviderNotConfiguredBanner";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";

const TIMEFRAMES = ["M15", "H1", "H4", "D1"] as const;

export function MarketsPage() {
  const { t } = useLocale();
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("H1");

  const providersQuery = useQuery({
    queryKey: ["providers", "status"],
    queryFn: getProvidersStatus,
  });

  const oandaConfigured = providersQuery.data?.oanda.configured === true;

  const candlesQuery = useQuery({
    queryKey: ["markets", symbol, timeframe],
    queryFn: () => getCandles(symbol, timeframe, 50),
    enabled: oandaConfigured,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="markets-title"
        title={t("markets.title")}
        description={t("markets.intro")}
      />
      {providersQuery.isSuccess && !oandaConfigured && (
        <ProviderNotConfiguredBanner
          title={t("markets.provider.notConfigured")}
          credentials={["OANDA_API_TOKEN", "OANDA_ACCOUNT_ID"]}
          testId="oanda-provider-not-configured"
        />
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground" htmlFor="markets-symbol">
          {t("common.symbol")}
          <Input
            id="markets-symbol"
            data-testid="markets-symbol-input"
            className="sm:w-40"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            disabled={!oandaConfigured}
          />
        </label>
        <label
          className="flex flex-col gap-1 text-xs text-muted-foreground"
          htmlFor="markets-timeframe"
        >
          {t("common.timeframe")}
          <select
            id="markets-timeframe"
            data-testid="markets-timeframe-select"
            className="h-11 rounded-md border border-border bg-input px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 sm:h-9 sm:w-28"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value as (typeof TIMEFRAMES)[number])}
            disabled={!oandaConfigured}
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
      </div>
      {oandaConfigured && candlesQuery.isLoading && (
        <div className="flex flex-col gap-1.5" data-testid="markets-loading">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}
      {oandaConfigured && candlesQuery.isError && (
        <p className="text-sm text-destructive">
          {(candlesQuery.error as Error).message || t("common.error.load")}
        </p>
      )}
      {candlesQuery.data && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="min-w-full text-start text-sm text-foreground">
            <thead className="bg-muted text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{t("markets.table.time")}</th>
                <th className="px-3 py-2">{t("markets.table.open")}</th>
                <th className="px-3 py-2">{t("markets.table.high")}</th>
                <th className="px-3 py-2">{t("markets.table.low")}</th>
                <th className="px-3 py-2">{t("markets.table.close")}</th>
              </tr>
            </thead>
            <tbody>
              {candlesQuery.data.candles.slice(-20).map((c) => (
                <tr key={c.ts} className="border-t border-border">
                  <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">{c.ts}</td>
                  <td className="px-3 py-1.5 font-mono">{c.open}</td>
                  <td className="px-3 py-1.5 font-mono">{c.high}</td>
                  <td className="px-3 py-1.5 font-mono">{c.low}</td>
                  <td className="px-3 py-1.5 font-mono">{c.close}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
