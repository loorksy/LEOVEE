import { useQuery } from "@tanstack/react-query";
import { getEntitlements } from "@/api/billing";
import { formatPlanLabel } from "@/features/admin/AdminEntitlementsPanel";
import { TelegramSettings } from "@/features/telegram/TelegramSettings";
import { useLocale } from "@/i18n/context";

export function SettingsPage() {
  const { t } = useLocale();
  const entitlementsQuery = useQuery({
    queryKey: ["billing", "entitlements"],
    queryFn: getEntitlements,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">{t("settings.title")}</h1>
        <p className="text-sm text-slate-400">{t("settings.intro")}</p>
      </header>
      {entitlementsQuery.isLoading && <p className="text-slate-400">{t("common.loading")}</p>}
      {entitlementsQuery.isError && (
        <p className="text-amber-400">{(entitlementsQuery.error as Error).message}</p>
      )}
      {entitlementsQuery.data && (
        <section className="max-w-lg rounded border border-slate-800 bg-leovee-panel p-6">
          <h2 className="text-lg font-medium text-slate-100">{t("settings.plan")}</h2>
          <p className="mt-2 text-sm text-slate-300" data-testid="plan-label">
            {formatPlanLabel(entitlementsQuery.data)}
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {Object.entries(entitlementsQuery.data.limits ?? {}).map(([metric, limit]) => (
              <div key={metric}>
                <dt className="text-slate-500">{metric}</dt>
                <dd className="text-slate-100">{String(limit)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-slate-500" data-testid="settings-broker-policy">
            {t("settings.brokerPolicy")}
          </p>
        </section>
      )}

      <section className="max-w-lg rounded border border-slate-800 bg-leovee-panel p-6">
        <TelegramSettings />
      </section>
</div>
  );
}
