import { apiFetch } from "@/api/httpClient";
import type { SemanticAnnotation } from "@/chart";

export async function listChartAnnotations(
  analysisId?: string,
): Promise<{ items: SemanticAnnotation[] }> {
  return apiFetch<{ items: SemanticAnnotation[] }>("/api/v1/chart/annotations", {
    query: analysisId ? { analysis_id: analysisId } : undefined,
  });
}

export type ChartSemanticOperationPayload = {
  semantic_type: string;
  geometry: { anchors: Array<{ ts: string; price: number; timeframe?: string | null }> };
  style?: Record<string, unknown>;
};

export async function buildSemanticModel(params: {
  symbol: string;
  timeframe: string;
  as_of: string;
  engines: Record<string, unknown>;
}): Promise<{ model: { version: number; operations: ChartSemanticOperationPayload[] } }> {
  return apiFetch("/api/v1/chart/semantic/build", { method: "POST", body: params });
}

export async function persistSemanticModel(
  model: Record<string, unknown>,
  options: { analysisId?: string; recommendationId?: string } = {},
): Promise<{ ids: string[]; count: number; version: number }> {
  return apiFetch("/api/v1/chart/semantic/persist", {
    method: "POST",
    body: { model },
    query: {
      analysis_id: options.analysisId,
      recommendation_id: options.recommendationId,
    },
  });
}
