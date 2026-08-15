import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardInset, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { AdminAgentRun } from "@/features/admin/types";
import { useLocale } from "@/i18n/context";

type Props = {
  runs: AdminAgentRun[];
  loading?: boolean;
  error?: boolean;
};

/** Platform-admin only — `GET /api/v1/admin/observability/agent-runs` (§36). */
export function AdminObservabilityPanel({ runs, loading, error }: Props) {
  const { t } = useLocale();
  return (
    <Card data-testid="admin-observability-panel">
      <CardHeader>
        <CardTitle>{t("admin.observability.title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {loading && (
          <div className="flex flex-col gap-2" data-testid="admin-observability-loading">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}
        {error && <p className="text-sm text-destructive">{t("common.error.load")}</p>}
        {!loading && !error && runs.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("admin.observability.empty")}</p>
        )}
        {!loading && runs.length > 0 && (
          <ul className="flex flex-col gap-2">
            {runs.map((run) => (
              <li key={run.id} data-testid={`admin-agent-run-${run.id}`}>
                <CardInset className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-sm text-foreground">{run.symbol}</p>
                    <Badge variant="neutral">{run.status}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t("admin.observability.tools")}: {run.tool_calls} ·{" "}
                    {t("admin.observability.memories")}: {run.memories_retrieved}
                  </p>
                </CardInset>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
