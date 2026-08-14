import { useMutation } from "@tanstack/react-query";
import { DEFAULT_SYMBOL } from "@/config/symbols";
import { useState } from "react";
import { previewReplay } from "@/api/replay";
import { ReplayPanel, type ReplayPreview } from "@/features/replay/ReplayPanel";
import { useLocale } from "@/i18n/context";

export function ReplayPage() {
  const { t } = useLocale();
  const [symbol, setSymbol] = useState<string>(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState("H1");
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 16));
  const [preview, setPreview] = useState<ReplayPreview | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      previewReplay({
        symbol,
        timeframe,
        as_of: new Date(asOf).toISOString(),
      }),
    onSuccess: (data) => setPreview(data),
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100" data-testid="replay-title">
          {t("replay.title")}
        </h1>
        <p className="text-sm text-slate-400">{t("replay.intro")}</p>
      </header>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <label className="text-xs text-slate-400">
          {t("common.symbol")}
          <input
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          />
        </label>
        <label className="text-xs text-slate-400">
          {t("common.timeframe")}
          <select
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          >
            {["M15", "H1", "H4", "D1"].map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-400">
          {t("replay.asof")}
          <input
            type="datetime-local"
            className="mt-1 block rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
        <button
          type="submit"
          data-testid="replay-preview-button"
          className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-slate-950"
          disabled={mutation.isPending}
        >
          {mutation.isPending ? t("common.loading") : t("replay.preview")}
        </button>
      </form>
      {mutation.isError ? (
        <p className="text-sm text-red-400">{(mutation.error as Error).message}</p>
      ) : null}
      <ReplayPanel preview={preview} loading={mutation.isPending} />
    </div>
  );
}
