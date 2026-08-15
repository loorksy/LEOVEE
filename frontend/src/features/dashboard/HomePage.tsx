import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

function HealthErrorMessage() {
  const { t } = useLocale();
  if (import.meta.env.DEV) {
    return (
      <p className="mt-2 text-sm text-destructive">
        {t("dashboard.error.dev")}{" "}
        <code className="rounded bg-muted px-1 font-mono text-xs">docker compose up</code>.
      </p>
    );
  }
  return <p className="mt-2 text-sm text-destructive">{t("dashboard.error.unreachable")}</p>;
}

export function HomePage() {
  const { t } = useLocale();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  const healthy =
    data?.status === "ok" &&
    data.checks?.database?.ok !== false &&
    data.checks?.redis?.ok !== false;

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="home-title"
        title={t("dashboard.title")}
        description={t("dashboard.subtitle")}
      />
      <Card>
        <CardHeader>
          <CardTitle className="uppercase tracking-wide text-muted-foreground">
            {t("dashboard.apiStatus")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && (
            <div className="flex flex-col gap-2" data-testid="home-health-loading">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          )}
          {isError && <HealthErrorMessage />}
          {data !== undefined && !isError && (
            <div className="flex flex-col gap-2">
              <p className={healthy ? "text-sm text-success" : "text-sm text-warning"}>
                {healthy ? t("dashboard.healthy") : t("dashboard.degraded")}
              </p>
              <pre className="overflow-x-auto rounded-lg bg-muted/50 p-3 font-mono text-xs text-muted-foreground">
                {JSON.stringify(data, null, 2)}
              </pre>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
