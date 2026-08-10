import type { AdminOverview } from "@/features/admin/types";

type Props = {
  overview: AdminOverview | null;
  loading?: boolean;
};

/** Platform-admin only — `GET /api/v1/admin/overview` (§36). */
export function AdminOverviewPanel({ overview, loading }: Props) {
  if (loading) {
    return <p className="text-slate-400">Loading platform overview…</p>;
  }
  return (
    <section
      data-testid="admin-overview-panel"
      className="rounded-lg border border-slate-800 bg-leovee-panel p-6"
    >
      <h2 className="text-lg font-semibold text-slate-100">Platform overview</h2>
      {overview ? (
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-slate-500">Conversations</dt>
            <dd className="text-slate-100">{overview.conversations}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Recommendations</dt>
            <dd className="text-slate-100">{overview.recommendations}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-2 text-slate-400">No overview data.</p>
      )}
    </section>
  );
}
