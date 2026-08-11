import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCandles } from "@/api/markets";
import { getProvidersStatus } from "@/api/providers";

const TIMEFRAMES = ["M15", "H1", "H4", "D1"] as const;

export function MarketsPage() {
  const [symbol, setSymbol] = useState("EURUSD");
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
        <h1 className="text-2xl font-semibold text-slate-100">Markets</h1>
        <p className="text-sm text-slate-400">
          Candle snapshots from `/api/v1/markets` (practice OANDA when configured).
        </p>
      </header>
      {providersQuery.isSuccess && !oandaConfigured && (
        <div
          className="rounded border border-amber-800/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-100"
          data-testid="oanda-provider-not-configured"
        >
          <p className="font-medium">Market data provider not configured</p>
          <p className="mt-1 text-amber-200/80">
            Set <code className="text-amber-100">OANDA_API_TOKEN</code> and{" "}
            <code className="text-amber-100">OANDA_ACCOUNT_ID</code> (practice) as GitHub Actions
            secrets and re-run Deploy staging.
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <label className="text-xs text-slate-400">
          Symbol
          <input
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            disabled={!oandaConfigured}
          />
        </label>
        <label className="text-xs text-slate-400">
          Timeframe
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
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
      {oandaConfigured && candlesQuery.isLoading && <p className="text-slate-400">Loading candles…</p>}
      {oandaConfigured && candlesQuery.isError && (
        <p className="text-amber-400">
          {(candlesQuery.error as Error).message || "Could not load market data."}
        </p>
      )}
      {candlesQuery.data && (
        <div className="overflow-auto rounded border border-slate-800">
          <table className="min-w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Open</th>
                <th className="px-3 py-2">High</th>
                <th className="px-3 py-2">Low</th>
                <th className="px-3 py-2">Close</th>
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