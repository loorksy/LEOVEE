import { apiFetch } from "@/api/httpClient";

export type AnalysisRunRequest = {
  symbol: string;
  timeframe?: string;
  complete_pipeline?: boolean;
};

export type AnalysisRunResponse = {
  agent_run_id: string;
  workspace_id: string;
  symbol: string;
  timeframe: string;
  perceive: Record<string, unknown>;
  recall: { label?: string; count: number; items?: unknown[] };
  engines: Record<string, unknown>;
  decision: {
    direction?: string;
    confidence?: number;
    [key: string]: unknown;
  };
  /** String in older clients; orchestrator returns `{ llm }` or `{ llm_unavailable }`. */
  narrative?: string | Record<string, unknown>;
  as_of: string;
  persistence?: Record<string, unknown>;
  reasoning?: Record<string, unknown>;
  recommendation_id?: string;
  thesis_id?: string;
};

export async function runAnalysis(body: AnalysisRunRequest): Promise<AnalysisRunResponse> {
  return apiFetch<AnalysisRunResponse>("/api/v1/analysis/run", {
    method: "POST",
    body: {
      symbol: body.symbol,
      timeframe: body.timeframe ?? "H1",
      complete_pipeline: body.complete_pipeline ?? false,
    },
  });
}
