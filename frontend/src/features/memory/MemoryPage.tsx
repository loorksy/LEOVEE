import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteMemory, getCalibrationCurve, listMemories } from "@/api/memory";
import { MemoryPanel } from "@/features/memory/MemoryPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLocale } from "@/i18n/context";

export function MemoryPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [recomputeStats, setRecomputeStats] = useState<Record<string, unknown> | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const memoriesQuery = useQuery({ queryKey: ["memory", "list"], queryFn: listMemories });
  const calibrationQuery = useQuery({
    queryKey: ["memory", "calibration"],
    queryFn: getCalibrationCurve,
  });

  async function handleDelete(id: string) {
    setDeleteError(null);
    try {
      const result = await deleteMemory(id);
      setRecomputeStats(result.recompute);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["memory", "list"] }),
        queryClient.invalidateQueries({ queryKey: ["memory", "calibration"] }),
      ]);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : t("memory.error.delete"));
    }
  }

  const loading = memoriesQuery.isLoading || calibrationQuery.isLoading;

  return (
    <div className="flex flex-1 flex-col gap-6 p-4 sm:p-6 lg:p-8">
      <PageHeader testId="memory-title" title={t("memory.title")} description={t("memory.intro")} />

      {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}

      {recomputeStats && (
        <div className="rounded-lg border border-border bg-muted/50 p-3" data-testid="recompute-stats">
          <p className="text-xs font-medium text-muted-foreground">{t("memory.recompute")}</p>
          <pre className="mt-1 overflow-x-auto font-mono text-xs text-foreground">
            {JSON.stringify(recomputeStats)}
          </pre>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2" data-testid="memory-loading">
          {Array.from({ length: 2 }).map((_, index) => (
            <Card key={index} className="flex flex-col gap-3 p-3">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </Card>
          ))}
        </div>
      ) : (
        <MemoryPanel
          memories={memoriesQuery.data?.items ?? []}
          bins={calibrationQuery.data?.bins ?? []}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}
