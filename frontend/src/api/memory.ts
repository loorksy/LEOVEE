import { apiFetch } from "@/api/httpClient";
import type { CalibrationBin, MemoryListItem } from "@/features/memory/types";

export async function listMemories(): Promise<{ items: MemoryListItem[] }> {
  return apiFetch<{ items: MemoryListItem[] }>("/api/v1/memory");
}

export async function getCalibrationCurve(): Promise<{ bins: CalibrationBin[] }> {
  return apiFetch<{ bins: CalibrationBin[] }>("/api/v1/memory/calibration");
}

export type MemoryRecomputeStats = Record<string, unknown>;

export async function deleteMemory(
  id: string,
): Promise<{ deleted: boolean; recompute: MemoryRecomputeStats }> {
  return apiFetch<{ deleted: boolean; recompute: MemoryRecomputeStats }>(`/api/v1/memory/${id}`, {
    method: "DELETE",
  });
}
