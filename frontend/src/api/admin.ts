import { apiFetch } from "@/api/httpClient";
import type {
  AdminAccess,
  AdminAgentRun,
  AdminAuditSummary,
  AdminConversationItem,
  AdminOverview,
} from "@/features/admin/types";

/** GET /api/v1/admin/me — any workspace member; never 403s (§36 permission matrix). */
export async function getAdminAccess(): Promise<AdminAccess> {
  return apiFetch<AdminAccess>("/api/v1/admin/me");
}

/** GET /api/v1/admin/audit/summary — support tier and above. */
export async function getAuditSummary(): Promise<AdminAuditSummary> {
  return apiFetch<AdminAuditSummary>("/api/v1/admin/audit/summary");
}

/** GET /api/v1/admin/overview — platform-admin only. */
export async function getAdminOverview(): Promise<AdminOverview> {
  return apiFetch<AdminOverview>("/api/v1/admin/overview");
}

/** GET /api/v1/admin/conversations — platform-admin only. */
export async function listAdminConversations(): Promise<{ items: AdminConversationItem[] }> {
  return apiFetch<{ items: AdminConversationItem[] }>("/api/v1/admin/conversations");
}

/** GET /api/v1/admin/observability/agent-runs — platform-admin only. */
export async function listAdminAgentRuns(): Promise<{ items: AdminAgentRun[] }> {
  return apiFetch<{ items: AdminAgentRun[] }>("/api/v1/admin/observability/agent-runs");
}
