import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health";
import { useLocale } from "@/i18n/context";

function HealthErrorMessage() {
  const { t } = useLocale();
  if (import.meta.env.DEV) {
    return (
      <p className="mt-2 text-amber-400">
        {t("dashboard.error.dev")}{" "}
        <code className="rounded bg-slate-800 px-1">docker compose up</code>.
      </p>
    );
  }
  return <p className="mt-2 text-amber-400">{t("dashboard.error.unreachable")}</p>;
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
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold" data-testid="home-title">
          {t("dashboard.title")}
        </h1>
        <p className="mt-1 text-slate-400">{t("dashboard.subtitle")}</p>
      </header>
      <section className="rounded-lg border border-slate-800 bg-leovee-panel p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          {t("dashboard.apiStatus")}
        </h2>
        {isLoading && <p className="mt-2 text-slate-400">{t("dashboard.checking")}</p>}
        {isError && <HealthErrorMessage />}
        {data !== undefined && !isError && (
          <div className="mt-2">
            <p className={healthy ? "text-emerald-400" : "text-amber-400"}>
              {healthy ? t("dashboard.healthy") : t("dashboard.degraded")}
            </p>
            <pre className="mt-2 overflow-auto text-sm text-slate-400">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
