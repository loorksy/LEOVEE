import { useState } from "react";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useQuery } from "@tanstack/react-query";
import { getCandles } from "@/api/markets";
import { getProvidersStatus } from "@/api/providers";
import { ProviderNotConfiguredBanner } from "@/components/ProviderNotConfiguredBanner";
import { useLocale } from "@/i18n/context";

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
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">{t("markets.title")}</h1>
        <p className="text-sm text-slate-400">{t("markets.intro")}</p>
      </header>
      {providersQuery.isSuccess && !oandaConfigured && (
        <ProviderNotConfiguredBanner
          title={t("markets.provider.notConfigured")}
          credentials={["OANDA_API_TOKEN", "OANDA_ACCOUNT_ID"]}
          testId="oanda-provider-not-configured"
        />
      )}
      <div className="flex flex-wrap gap-3">
        <label className="text-xs text-slate-400">
          {t("common.symbol")}
          <input
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            disabled={!oandaConfigured}
          />
        </label>
        <label className="text-xs text-slate-400">
          {t("common.timeframe")}
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
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
        <p className="text-slate-400">{t("common.loading")}</p>
      )}
      {oandaConfigured && candlesQuery.isError && (
        <p className="text-amber-400">
          {(candlesQuery.error as Error).message || t("common.error.load")}
        </p>
      )}
      {candlesQuery.data && (
        <div className="overflow-auto rounded border border-slate-800">
          <table className="min-w-full text-start text-sm text-slate-300">
            <thead className="bg-slate-900 text-xs uppercase text-slate-500">
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
                <tr key={c.ts} className="border-t border-slate-800">
                  <td className="px-3 py-1.5 font-mono text-xs">{c.ts}</td>
                  <td className="px-3 py-1.5">{c.open}</td>
                  <td className="px-3 py-1.5">{c.high}</td>
                  <td className="px-3 py-1.5">{c.low}</td>
                  <td className="px-3 py-1.5">{c.close}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
