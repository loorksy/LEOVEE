import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteMemory, getCalibrationCurve, listMemories } from "@/api/memory";
import { MemoryPanel } from "@/features/memory/MemoryPanel";
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
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">{t("memory.title")}</h1>
        <p className="mt-1 text-slate-400">{t("memory.intro")}</p>
      </header>
      {deleteError && <p className="text-amber-400">{deleteError}</p>}
      {loading && <p className="text-slate-400">{t("common.loading")}</p>}
      {recomputeStats && (
        <p className="text-xs text-slate-500" data-testid="recompute-stats">
          {t("memory.recompute")}: {JSON.stringify(recomputeStats)}
        </p>
      )}
      <MemoryPanel
        memories={memoriesQuery.data?.items ?? []}
        bins={calibrationQuery.data?.bins ?? []}
        onDelete={handleDelete}
      />
    </div>
  );
}
