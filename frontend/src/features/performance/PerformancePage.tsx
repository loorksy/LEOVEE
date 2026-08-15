import { useQuery } from "@tanstack/react-query";
import { getPerformanceSummary } from "@/api/performance";
import { PerformanceDashboard } from "@/features/performance/PerformanceDashboard";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLocale } from "@/i18n/context";

export function PerformancePage() {
  const { t } = useLocale();
  const summaryQuery = useQuery({
    queryKey: ["performance", "summary"],
    queryFn: getPerformanceSummary,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        testId="performance-title"
        title={t("performance.title")}
        description={
          <>
            {t("performance.introPrefix")}{" "}
            <code className="rounded bg-muted px-1 font-mono text-xs">
              /api/v1/performance/summary
            </code>{" "}
            {t("performance.introSuffix")}
          </>
        }
      />
      {summaryQuery.isError && (
        <p className="text-sm text-destructive" data-testid="performance-error">
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
