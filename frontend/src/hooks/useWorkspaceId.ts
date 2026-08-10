import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { listWorkspaces } from "@/api/workspaces";
import { useAuth } from "@/hooks/useAuth";

/** Resolve the current user's default workspace id (§6 — workspace-scoped resources). */
export function useWorkspaceId(): UseQueryResult<string | null> {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ["workspaces", "default"],
    queryFn: async () => {
      const { items } = await listWorkspaces();
      return items[0]?.id ?? null;
    },
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });
}
