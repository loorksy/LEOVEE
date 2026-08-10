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
  if (loading) {
    return <p className="text-slate-400">Loading replay preview…</p>;
  }
  if (!preview) {
    return <p className="text-slate-400">Select a replay time to preview historical state.</p>;
  }
  return (
    <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
      <h2 className="text-lg font-semibold text-slate-100">Historical replay</h2>
      <p className="text-xs text-slate-500">
        {preview.symbol} {preview.timeframe} · as of {preview.as_of}
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-slate-500">Visible candles</dt>
          <dd className="text-slate-100">{preview.candle_count}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Future candles hidden</dt>
          <dd className="text-slate-100">{preview.excluded_future_candles}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Memories recalled</dt>
          <dd className="text-slate-100">{preview.recall.counts.memories}</dd>
        </div>
      </dl>
    </section>
  );
}
