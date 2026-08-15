import { useQuery } from "@tanstack/react-query";
import { getEntitlements } from "@/api/billing";
import { formatPlanLabel } from "@/features/admin/AdminEntitlementsPanel";
import { TelegramSettings } from "@/features/telegram/TelegramSettings";
import { useLocale } from "@/i18n/context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

export function SettingsPage() {
  const { t } = useLocale();
  const entitlementsQuery = useQuery({
    queryKey: ["billing", "entitlements"],
    queryFn: getEntitlements,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader testId="settings-title" title={t("settings.title")} description={t("settings.intro")} />

      {entitlementsQuery.isLoading && (
        <div className="flex flex-col gap-2 sm:max-w-lg" data-testid="settings-loading">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}
      {entitlementsQuery.isError && (
        <p className="text-sm text-destructive">{(entitlementsQuery.error as Error).message}</p>
      )}
      {entitlementsQuery.data && (
        <Card className="sm:max-w-lg">
          <CardHeader>
            <CardTitle>{t("settings.plan")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-sm text-foreground" data-testid="plan-label">
              {formatPlanLabel(entitlementsQuery.data)}
            </p>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              {Object.entries(entitlementsQuery.data.limits ?? {}).map(([metric, limit]) => (
                <div key={metric}>
                  <dt className="text-muted-foreground">{metric}</dt>
                  <dd className="font-mono text-foreground">{String(limit)}</dd>
                </div>
              ))}
            </dl>
            <p className="text-xs text-muted-foreground" data-testid="settings-broker-policy">
              {t("settings.brokerPolicy")}
            </p>
          </CardContent>
        </Card>
      )}

      <TelegramSettings />
    </div>
  );
}
