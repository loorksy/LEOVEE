import { useEffect } from "react";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { clearWorkspaceId, setWorkspaceId } from "@/api/workspaceStore";
import { useAuth } from "@/hooks/useAuth";

/** Keep the http client's workspace header in sync with the default membership. */
export function WorkspaceBootstrap() {
  const { isAuthenticated } = useAuth();
  const workspaceQuery = useWorkspaceId();

  useEffect(() => {
    if (!isAuthenticated) {
      clearWorkspaceId();
      return;
    }
    if (workspaceQuery.data) {
      setWorkspaceId(workspaceQuery.data);
    }
  }, [isAuthenticated, workspaceQuery.data]);

  return null;
}
