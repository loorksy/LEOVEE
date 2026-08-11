export type Entitlements = {
  plan_code: string;
  plan_name: string;
  limits?: Record<string, number>;
  subscription_status?: string;
};

/** Response shape of `GET /api/v1/admin/me` — drives the UI permission matrix. */
export type AdminAccess = {
  role: string;
  is_support: boolean;
  is_platform_admin: boolean;
};

/** Support tier and above — `GET /api/v1/admin/audit/summary`. */
export type AdminAuditSummary = {
  users: number;
  organizations: number;
  workspaces: number;
  workspace_id: string;
};

/** Platform-admin only — `GET /api/v1/admin/overview`. */
export type AdminOverview = {
  conversations: number;
  recommendations: number;
  workspace_id: string;
};

/** Platform-admin only — `GET /api/v1/admin/conversations`. */
export type AdminConversationItem = {
  id: string;
  title: string;
  mode: string;
};

/** Platform-admin only — `GET /api/v1/admin/observability/agent-runs`. */
export type AdminAgentRun = {
  id: string;
  symbol: string;
  status: string;
  tool_calls: number;
  memories_retrieved: number;
};
