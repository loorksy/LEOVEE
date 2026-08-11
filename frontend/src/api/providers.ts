import { apiFetch } from "@/api/httpClient";

export type ProviderStatus = {
  configured: boolean;
  status: "ok" | "not_configured" | string;
  environment?: string;
};

export type ProvidersStatus = {
  finnhub: ProviderStatus;
  oanda: ProviderStatus;
  anthropic: ProviderStatus;
  openai: ProviderStatus;
  openrouter: ProviderStatus & { mode?: string | null };
};

export async function getProvidersStatus(): Promise<ProvidersStatus> {
  return apiFetch("/api/v1/providers/status");
}
