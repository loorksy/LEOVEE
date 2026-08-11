import { apiFetch } from "@/api/httpClient";
import type { Entitlements } from "@/features/admin/types";

export async function getEntitlements(): Promise<Entitlements> {
  return apiFetch("/api/v1/billing/entitlements");
}
