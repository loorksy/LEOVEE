import { useLocale } from "@/i18n/context";

export type ReplayPreview = {
  symbol: string;
  timeframe: string;
  as_of: string;
  candle_count: number;
  excluded_future_candles: number;
  candles: { ts: string; close: number }[];
  recall: {
    counts: { memories: number; lessons: number; episodes: number };
  };
};

type Props = {
  preview: ReplayPreview | null;
  loading?: boolean;
};

export function ReplayPanel({ preview, loading }: Props) {
  const { t } = useLocale();
  if (loading) {
    return <p className="text-slate-400">{t("replay.loading")}</p>;
  }
  if (!preview) {
    return <p className="text-slate-400">{t("replay.empty")}</p>;
  }
  return (
    <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
      <h2 className="text-lg font-semibold text-slate-100">{t("replay.historical")}</h2>
      <p className="text-xs text-slate-500">
        {preview.symbol} {preview.timeframe} ·{" "}
        {t("replay.asof.value", { timestamp: preview.as_of })}
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate-500">{t("replay.candles.visible")}</dt>
          <dd className="text-slate-100">{preview.candle_count}</dd>
        </div>
        <div>
          <dt className="text-slate-500">{t("replay.candles.hidden")}</dt>
          <dd className="text-slate-100">{preview.excluded_future_candles}</dd>
        </div>
        <div>
          <dt className="text-slate-500">{t("replay.memories")}</dt>
          <dd className="text-slate-100">{preview.recall.counts.memories}</dd>
        </div>
      </dl>
    </section>
  );
}
