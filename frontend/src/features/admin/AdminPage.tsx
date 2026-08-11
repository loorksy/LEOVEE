import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAdminOverview,
  getAdminSecrets,
  getAuditSummary,
  listAdminAgentRuns,
  listAdminConversations,
  putAdminSecrets,
} from "@/api/admin";
import { getEntitlements } from "@/api/billing";
import { AdminConversationsPanel } from "@/features/admin/AdminConversationsPanel";
import { AdminEntitlementsPanel } from "@/features/admin/AdminEntitlementsPanel";
import { AdminObservabilityPanel } from "@/features/admin/AdminObservabilityPanel";
import { AdminOverviewPanel } from "@/features/admin/AdminOverviewPanel";
import { AdminSecretsPanel } from "@/features/admin/AdminSecretsPanel";
import { useAdminAccess } from "@/features/admin/useAdminAccess";

/**
 * `/admin` — plan/billing is visible to every workspace member; audit,
 * overview, conversations, and observability are gated by the permission
 * matrix from `GET /api/v1/admin/me` (§36 phase — support vs platform-admin).
 * Backend RBAC (`require_support_audit` / `require_platform_admin`) is the
 * source of truth; this page hides/disables sections the user cannot use so
 * they never see an avoidable 403.
 */
export function AdminPage() {
  const queryClient = useQueryClient();
  const accessQuery = useAdminAccess();
  const isSupport = accessQuery.data?.is_support ?? false;
  const isPlatformAdmin = accessQuery.data?.is_platform_admin ?? false;
  const [secretsSuccess, setSecretsSuccess] = useState<string | null>(null);
  const [secretsError, setSecretsError] = useState<string | null>(null);

  const entitlementsQuery = useQuery({
    queryKey: ["billing", "entitlements"],
    queryFn: getEntitlements,
  });

  const auditQuery = useQuery({
    queryKey: ["admin", "audit-summary"],
    queryFn: getAuditSummary,
    enabled: isSupport,
  });

  const overviewQuery = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: getAdminOverview,
    enabled: isPlatformAdmin,
  });

  const conversationsQuery = useQuery({
    queryKey: ["admin", "conversations"],
    queryFn: listAdminConversations,
    enabled: isPlatformAdmin,
  });

  const agentRunsQuery = useQuery({
    queryKey: ["admin", "agent-runs"],
    queryFn: listAdminAgentRuns,
    enabled: isPlatformAdmin,
  });

  const secretsQuery = useQuery({
    queryKey: ["admin", "secrets"],
    queryFn: getAdminSecrets,
    enabled: isPlatformAdmin,
  });

  const secretsMutation = useMutation({
    mutationFn: putAdminSecrets,
    onSuccess: async () => {
      setSecretsError(null);
      setSecretsSuccess("Secrets saved. Providers will use the new values immediately.");
      await queryClient.invalidateQueries({ queryKey: ["admin", "secrets"] });
    },
    onError: (err: unknown) => {
      setSecretsSuccess(null);
      setSecretsError(err instanceof Error ? err.message : "Failed to save secrets");
    },
  });

  return (
    <div className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-100">Admin & billing</h1>
        <p className="mt-1 text-slate-400">
          Plan, entitlements, and platform administration (§36–§38). Sections below reflect your
          role — <code>{accessQuery.data?.role ?? "…"}</code>.
        </p>
      </header>

      {accessQuery.isError && (
        <p className="text-amber-400">Could not load your admin permissions.</p>
      )}

      <AdminEntitlementsPanel
        entitlements={entitlementsQuery.data ?? null}
        auditSummary={isSupport ? auditQuery.data ?? null : null}
        loading={entitlementsQuery.isLoading}
      />

      {!isSupport && !accessQuery.isLoading && (
        <p data-testid="admin-access-restricted" className="text-sm text-slate-500">
          Platform audit and admin sections are hidden — they require Support, Admin, or Super
          Admin workspace role.
        </p>
      )}

      {isSupport && !isPlatformAdmin && (
        <p data-testid="admin-platform-only-hint" className="text-sm text-slate-500">
          Overview, conversations, agent observability, and secrets require the platform Admin or
          Super Admin role and are hidden for Support.
        </p>
      )}

      {isPlatformAdmin && (
        <>
          <AdminSecretsPanel
            items={secretsQuery.data?.items ?? []}
            oandaEnvironment={secretsQuery.data?.oanda_environment ?? "practice"}
            loading={secretsQuery.isLoading}
            saving={secretsMutation.isPending}
            error={secretsError ?? (secretsQuery.isError ? "Could not load secrets status." : null)}
            success={secretsSuccess}
            onSave={async (secrets) => {
              setSecretsSuccess(null);
              setSecretsError(null);
              await secretsMutation.mutateAsync(secrets);
            }}
          />
          <AdminOverviewPanel overview={overviewQuery.data ?? null} loading={overviewQuery.isLoading} />
          <AdminConversationsPanel
            conversations={conversationsQuery.data?.items ?? []}
            loading={conversationsQuery.isLoading}
            error={conversationsQuery.isError}
          />
          <AdminObservabilityPanel
            runs={agentRunsQuery.data?.items ?? []}
            loading={agentRunsQuery.isLoading}
            error={agentRunsQuery.isError}
          />
        </>
      )}
    </div>
  );
}
