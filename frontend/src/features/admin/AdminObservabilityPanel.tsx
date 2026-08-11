import type { AdminAgentRun } from "@/features/admin/types";

type Props = {
  runs: AdminAgentRun[];
  loading?: boolean;
  error?: boolean;
};

/** Platform-admin only — `GET /api/v1/admin/observability/agent-runs` (§36). */
export function AdminObservabilityPanel({ runs, loading, error }: Props) {
  return (
    <section
      data-testid="admin-observability-panel"
      className="rounded-lg border border-slate-800 bg-leovee-panel p-6"
    >
      <h2 className="text-lg font-semibold text-slate-100">Agent observability</h2>
      {loading && <p className="mt-2 text-slate-400">Loading agent runs…</p>}
      {error && <p className="mt-2 text-amber-400">Could not load agent runs.</p>}
      {!loading && !error && runs.length === 0 && (
        <p className="mt-2 text-slate-400">No agent runs recorded yet.</p>
      )}
      <ul className="mt-4 space-y-2 text-sm">
        {runs.map((run) => (
          <li
            key={run.id}
            data-testid={`admin-agent-run-${run.id}`}
            className="flex items-center justify-between rounded border border-slate-800 p-3"
          >
            <div>
              <p className="text-slate-100">{run.symbol}</p>
              <p className="text-xs text-slate-500">{run.status}</p>
            </div>
            <p className="text-xs text-slate-500">
              tools: {run.tool_calls} · memories: {run.memories_retrieved}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
