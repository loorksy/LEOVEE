import { apiFetch } from "@/api/httpClient";

export type WorkspaceSummary = {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
  owner_user_id: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export async function listWorkspaces(): Promise<{ items: WorkspaceSummary[] }> {
  return apiFetch<{ items: WorkspaceSummary[] }>("/api/v1/workspaces");
}
