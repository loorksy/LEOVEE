import { apiFetch } from "@/api/httpClient";
import type { AlertData } from "@/features/alerts/types";

export async function listAlerts(): Promise<{ items: AlertData[] }> {
  return apiFetch<{ items: AlertData[] }>("/api/v1/alerts");
}

export type CreateAlertInput = {
  type: string;
  symbol?: string;
  condition?: Record<string, unknown>;
  channels?: Record<string, unknown>;
};

export async function createAlert(input: CreateAlertInput): Promise<{ id: string }> {
  return apiFetch<{ id: string }>("/api/v1/alerts", {
    method: "POST",
    body: input,
  });
}

/** Mock trigger for demo purposes — evaluates the alert's condition against `price` (phase 30). */
export async function triggerAlert(id: string, price: number): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/v1/alerts/${id}/trigger`, {
    method: "POST",
    body: { price },
  });
}
