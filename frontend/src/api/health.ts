import { apiUrl } from "@/api/config";

export type HealthReadyResponse = {
  status: string;
  checks?: {
    database?: { ok: boolean; error: string | null };
    redis?: { ok: boolean; error: string | null };
  };
};

export async function fetchHealth(): Promise<HealthReadyResponse> {
  const response = await fetch(apiUrl("/health/ready"));
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json() as Promise<HealthReadyResponse>;
}
