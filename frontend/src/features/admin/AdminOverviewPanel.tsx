import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { AdminOverview } from "@/features/admin/types";
import { useLocale } from "@/i18n/context";

type Props = {
  overview: AdminOverview | null;
  loading?: boolean;
};

/** Platform-admin only — `GET /api/v1/admin/overview` (§36). */
export function AdminOverviewPanel({ overview, loading }: Props) {
  const { t } = useLocale();
  return (
    <Card data-testid="admin-overview-panel">
      <CardHeader>
        <CardTitle>{t("admin.overview.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="flex flex-col gap-2" data-testid="admin-overview-loading">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}
        {!loading && overview && (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground">{t("admin.overview.conversations")}</dt>
              <dd className="font-mono text-foreground">{overview.conversations}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t("admin.overview.recommendations")}</dt>
              <dd className="font-mono text-foreground">{overview.recommendations}</dd>
            </div>
          </dl>
        )}
        {!loading && !overview && (
          <p className="text-sm text-muted-foreground">{t("admin.overview.empty")}</p>
        )}
      </CardContent>
    </Card>
  );
}
