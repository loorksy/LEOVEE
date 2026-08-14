import { apiFetch } from "@/api/httpClient";

export type AnalysisRunRequest = {
  symbol: string;
  timeframe?: string;
  complete_pipeline?: boolean;
};

export type EvidenceCheckStatus = "ok" | "warning" | "stale" | "absent";

export type EvidenceCheck = {
  name: string;
  status: EvidenceCheckStatus;
  blocking: boolean;
  detail: string;
  value?: Record<string, unknown>;
};

export type EvidenceReport = {
  blocked: boolean;
  block_reason: string | null;
  warnings: string[];
  checks: EvidenceCheck[];
};

/** Pull the evidence report out of the engines bag, defensively — an older run
 *  (before the gate landed) simply has no `evidence` key. */
export function evidenceFromEngines(
  engines: Record<string, unknown> | undefined,
): EvidenceReport | null {
  const raw = engines?.evidence;
  if (!raw || typeof raw !== "object") return null;
  const report = raw as Partial<EvidenceReport>;
  if (!Array.isArray(report.checks)) return null;
  return {
    blocked: Boolean(report.blocked),
    block_reason: typeof report.block_reason === "string" ? report.block_reason : null,
    warnings: Array.isArray(report.warnings) ? report.warnings : [],
    checks: report.checks as EvidenceCheck[],
  };
}

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
    confidence?: number | null;
    degraded?: boolean;
    degraded_reason?: string;
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
      ...(body.timeframe ? { timeframe: body.timeframe } : {}),
      complete_pipeline: body.complete_pipeline ?? false,
    },
  });
}
