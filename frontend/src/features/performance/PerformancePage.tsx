import { useQuery } from "@tanstack/react-query";
import { getPerformanceSummary } from "@/api/performance";
import { PerformanceDashboard } from "@/features/performance/PerformanceDashboard";
import { useLocale } from "@/i18n/context";

export function PerformancePage() {
  const { t } = useLocale();
  const summaryQuery = useQuery({
    queryKey: ["performance", "summary"],
    queryFn: getPerformanceSummary,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100" data-testid="performance-title">
          {t("performance.title")}
        </h1>
        <p className="mt-1 text-slate-400">
          {t("performance.introPrefix")} <code>/api/v1/performance/summary</code>{" "}
          {t("performance.introSuffix")}
        </p>
      </header>
      {summaryQuery.isError && (
        <p className="text-amber-400" data-testid="performance-error">
          {t("common.error.load")}
        </p>
      )}
      <PerformanceDashboard
        summary={summaryQuery.data ?? null}
        loading={summaryQuery.isLoading}
      />
    </div>
  );
}
