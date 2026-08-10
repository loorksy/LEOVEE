import type { PerformanceSummary } from "./types";

type Props = {
  summary: PerformanceSummary | null;
  loading?: boolean;
};

export function PerformanceDashboard({ summary, loading }: Props) {
  if (loading) {
    return <p className="text-slate-400">Loading performance metrics…</p>;
  }
  if (!summary) {
    return <p className="text-slate-400">No performance data.</p>;
  }
  return (
    <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
      <h2 className="text-lg font-semibold text-slate-100">Performance</h2>
      <p className="text-xs text-slate-500">As of {summary.as_of}</p>
      <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-slate-500">Trade ideas</dt>
          <dd className="text-slate-100">{summary.trade_ideas}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Calibration rate</dt>
          <dd className="text-slate-100">{summary.calibration.rate.toFixed(3)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Predicted (bins)</dt>
          <dd className="text-slate-100">{summary.calibration.predicted_total}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Realized success</dt>
          <dd className="text-slate-100">{summary.calibration.realized_success_total}</dd>
        </div>
      </dl>
      <div className="mt-4 flex h-24 items-end gap-1">
        {summary.calibration.bins.map((bin) => (
          <div
            key={`${bin.bin_lower}-${bin.bin_upper}`}
            className="flex-1 bg-emerald-600"
            style={{
              height: `${Math.max(8, (bin.predicted_count / Math.max(1, summary.calibration.predicted_total)) * 100)}%`,
            }}
            title={`${bin.bin_lower}-${bin.bin_upper}`}
          />
        ))}
      </div>
    </section>
  );
}
