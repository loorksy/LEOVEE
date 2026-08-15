import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { Entitlements } from "@/features/admin/types";
import { useLocale } from "@/i18n/context";

export type { Entitlements };

export function formatPlanLabel(entitlements: Entitlements): string {
  return `${entitlements.plan_name} (${entitlements.plan_code})`;
}

type Props = {
  entitlements: Entitlements | null;
  auditSummary?: { users?: number; workspaces?: number } | null;
  loading?: boolean;
};

export function AdminEntitlementsPanel({ entitlements, auditSummary, loading }: Props) {
  const { t } = useLocale();
  return (
    <Card data-testid="admin-entitlements-panel">
      <CardHeader>
        <CardTitle>{t("admin.entitlements.title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {loading && (
          <div className="flex flex-col gap-2" data-testid="admin-entitlements-loading">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}
        {!loading && entitlements && (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground">{t("admin.entitlements.plan")}</dt>
              <dd className="text-foreground">{formatPlanLabel(entitlements)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t("admin.entitlements.subscription")}</dt>
              <dd className="text-foreground">{entitlements.subscription_status ?? "—"}</dd>
            </div>
          </dl>
        )}
        {!loading && !entitlements && (
          <p className="text-sm text-muted-foreground">{t("admin.entitlements.empty")}</p>
        )}
        {!loading && entitlements?.limits && (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {Object.entries(entitlements.limits).map(([metric, limit]) => (
              <div key={metric}>
                <dt className="text-muted-foreground">{metric}</dt>
                <dd className="font-mono text-foreground">{String(limit)}</dd>
              </div>
            ))}
          </dl>
        )}
        {!loading && auditSummary && (
          <p className="text-xs text-muted-foreground" data-testid="admin-audit-summary">
            {t("admin.entitlements.audit")} — {t("admin.entitlements.users")}:{" "}
            {auditSummary.users ?? 0}, {t("admin.entitlements.workspaces")}:{" "}
            {auditSummary.workspaces ?? 0}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
