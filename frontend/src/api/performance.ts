import { apiFetch } from "@/api/httpClient";
import type { PerformanceSummary } from "@/features/performance/types";

export async function getPerformanceSummary(): Promise<PerformanceSummary> {
  return apiFetch<PerformanceSummary>("/api/v1/performance/summary");
}
