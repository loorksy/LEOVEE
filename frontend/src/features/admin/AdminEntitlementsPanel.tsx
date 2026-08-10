export type Entitlements = {
  plan_code: string;
  plan_name: string;
  limits?: Record<string, number>;
  subscription_status?: string;
};

export function formatPlanLabel(entitlements: Entitlements): string {
  return `${entitlements.plan_name} (${entitlements.plan_code})`;
}

type Props = {
  entitlements: Entitlements | null;
  auditSummary?: { users?: number; workspaces?: number } | null;
  loading?: boolean;
};

export function AdminEntitlementsPanel({ entitlements, auditSummary, loading }: Props) {
  if (loading) {
    return <p className="text-slate-400">Loading admin & billing…</p>;
  }
  return (
    <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
      <h2 className="text-lg font-semibold text-slate-100">Plan & admin</h2>
      {entitlements ? (
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-slate-500">Plan</dt>
            <dd className="text-slate-100">{formatPlanLabel(entitlements)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Subscription</dt>
            <dd className="text-slate-100">{entitlements.subscription_status ?? "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-2 text-slate-400">No entitlement data.</p>
      )}
      {entitlements?.limits && (
        <ul className="mt-4 list-inside list-disc text-sm text-slate-300">
          {Object.entries(entitlements.limits).map(([key, value]) => (
            <li key={key}>
              {key}: {value}
            </li>
          ))}
        </ul>
      )}
      {auditSummary && (
        <p className="mt-4 text-xs text-slate-500">
          Platform audit — users: {auditSummary.users ?? 0}, workspaces:{" "}
          {auditSummary.workspaces ?? 0}
        </p>
      )}
    </section>
  );
}
