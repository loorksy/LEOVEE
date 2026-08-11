import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { getAdminAccess } from "@/api/admin";
import { useAuth } from "@/hooks/useAuth";
import type { AdminAccess } from "@/features/admin/types";

/**
 * Resolve the current user's admin capabilities (§36 permission matrix).
 * `admin/me` never 403s, so this hook is safe to call unconditionally for
 * any signed-in user — it is how the UI decides which sections/actions to
 * hide or disable (support-only vs platform-admin) ahead of the backend's
 * own `require_support_audit` / `require_platform_admin` enforcement.
 */
export function useAdminAccess(): UseQueryResult<AdminAccess> {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ["admin", "me"],
    queryFn: getAdminAccess,
    enabled: isAuthenticated,
    staleTime: 60 * 1000,
  });
}
