import { apiFetch } from "@/api/httpClient";
import type { Entitlements } from "@/features/admin/types";

/** GET /api/v1/billing/entitlements — any workspace member (§37/§38). */
export async function getEntitlements(): Promise<Entitlements> {
  return apiFetch<Entitlements>("/api/v1/billing/entitlements");
}
