/** In-memory active workspace id for attaching `X-Workspace-Id` on API calls. */

let activeWorkspaceId: string | null = null;

export const WORKSPACE_CHANGED_EVENT = "leovee-workspace-changed";

export function getWorkspaceId(): string | null {
  return activeWorkspaceId;
}

export function setWorkspaceId(workspaceId: string | null): void {
  activeWorkspaceId = workspaceId;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(WORKSPACE_CHANGED_EVENT));
  }
}

export function clearWorkspaceId(): void {
  setWorkspaceId(null);
}
