import { useQuery } from "@tanstack/react-query";
import { getPerformanceSummary } from "@/api/performance";
import { PerformanceDashboard } from "@/features/performance/PerformanceDashboard";

export function PerformancePage() {
  const summaryQuery = useQuery({
    queryKey: ["performance", "summary"],
    queryFn: getPerformanceSummary,
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Performance</h1>
        <p className="mt-1 text-slate-400">
          Recommendation and calibration aggregates from{" "}
          <code>/api/v1/performance/summary</code> (§33).
        </p>
      </header>
      {summaryQuery.isError && (
        <p className="text-amber-400">Could not load performance summary.</p>
      )}
      <PerformanceDashboard
        summary={summaryQuery.data ?? null}
        loading={summaryQuery.isLoading}
      />
    </div>
  );
}
