import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { clearTokens, setTokens } from "@/api/authStore";
import { AdminPage } from "./AdminPage";
import * as adminApi from "@/api/admin";
import * as billingApi from "@/api/billing";

function mockEntitlements() {
  vi.spyOn(billingApi, "getEntitlements").mockResolvedValue({
    plan_code: "FREE",
    plan_name: "Free",
    limits: { messages_per_month: 100 },
    subscription_status: "FREE",
  });
}

describe("AdminPage permission matrix", () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it("hides audit and platform-admin sections for a plain USER role", async () => {
    setTokens({ access_token: "tok", refresh_token: "r" });
    mockEntitlements();
    vi.spyOn(adminApi, "getAdminAccess").mockResolvedValue({
      role: "USER",
      is_support: false,
      is_platform_admin: false,
    });
    const auditSpy = vi.spyOn(adminApi, "getAuditSummary");
    const overviewSpy = vi.spyOn(adminApi, "getAdminOverview");
    const conversationsSpy = vi.spyOn(adminApi, "listAdminConversations");
    const agentRunsSpy = vi.spyOn(adminApi, "listAdminAgentRuns");
    const secretsSpy = vi.spyOn(adminApi, "getAdminSecrets");

    renderWithProviders(<AdminPage />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Admin & billing" }),
    ).toBeInTheDocument();
    await screen.findByTestId("admin-access-restricted");

    expect(screen.queryByTestId("admin-overview-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-conversations-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-observability-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-secrets-panel")).not.toBeInTheDocument();
    expect(auditSpy).not.toHaveBeenCalled();
    expect(overviewSpy).not.toHaveBeenCalled();
    expect(conversationsSpy).not.toHaveBeenCalled();
    expect(agentRunsSpy).not.toHaveBeenCalled();
    expect(secretsSpy).not.toHaveBeenCalled();
  });

  it("shows audit summary but hides platform-admin-only sections for SUPPORT", async () => {
    setTokens({ access_token: "tok", refresh_token: "r" });
    mockEntitlements();
    vi.spyOn(adminApi, "getAdminAccess").mockResolvedValue({
      role: "SUPPORT",
      is_support: true,
      is_platform_admin: false,
    });
    const auditSpy = vi.spyOn(adminApi, "getAuditSummary").mockResolvedValue({
      users: 3,
      organizations: 1,
      workspaces: 1,
      workspace_id: "ws-1",
    });
    const overviewSpy = vi.spyOn(adminApi, "getAdminOverview");
    const conversationsSpy = vi.spyOn(adminApi, "listAdminConversations");
    const agentRunsSpy = vi.spyOn(adminApi, "listAdminAgentRuns");

    renderWithProviders(<AdminPage />);

    await screen.findByTestId("admin-platform-only-hint");
    await waitFor(() => expect(auditSpy).toHaveBeenCalled());
    expect(await screen.findByText(/Platform audit — users: 3/)).toBeInTheDocument();

    expect(screen.queryByTestId("admin-overview-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-conversations-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-observability-panel")).not.toBeInTheDocument();
    expect(overviewSpy).not.toHaveBeenCalled();
    expect(conversationsSpy).not.toHaveBeenCalled();
    expect(agentRunsSpy).not.toHaveBeenCalled();
    expect(screen.queryByTestId("admin-access-restricted")).not.toBeInTheDocument();
  });

  it("shows every section for a platform ADMIN role", async () => {
    setTokens({ access_token: "tok", refresh_token: "r" });
    mockEntitlements();
    vi.spyOn(adminApi, "getAdminAccess").mockResolvedValue({
      role: "ADMIN",
      is_support: true,
      is_platform_admin: true,
    });
    vi.spyOn(adminApi, "getAuditSummary").mockResolvedValue({
      users: 5,
      organizations: 2,
      workspaces: 2,
      workspace_id: "ws-1",
    });
    vi.spyOn(adminApi, "getAdminOverview").mockResolvedValue({
      conversations: 7,
      recommendations: 4,
      workspace_id: "ws-1",
    });
    vi.spyOn(adminApi, "listAdminConversations").mockResolvedValue({
      items: [{ id: "c-1", title: "EURUSD bias", mode: "CHAT" }],
    });
    vi.spyOn(adminApi, "listAdminAgentRuns").mockResolvedValue({
      items: [
        { id: "r-1", symbol: "EURUSD", status: "COMPLETE", tool_calls: 2, memories_retrieved: 3 },
      ],
    });
    vi.spyOn(adminApi, "getAdminSecrets").mockResolvedValue({
      items: [
        { key: "OPENAI_API_KEY", configured: false, updated_at: null },
        { key: "OANDA_API_TOKEN", configured: true, updated_at: "2026-08-11T00:00:00Z" },
      ],
      oanda_environment: "practice",
      oanda_execution_enabled: false,
      managed_keys: ["OPENAI_API_KEY", "OANDA_API_TOKEN"],
    });

    renderWithProviders(<AdminPage />);

    expect(await screen.findByTestId("admin-secrets-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("admin-overview-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("admin-conversations-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("admin-observability-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("admin-conversation-c-1")).toBeInTheDocument();
    expect(await screen.findByTestId("admin-agent-run-r-1")).toBeInTheDocument();
    expect(await screen.findByTestId("secret-status-OANDA_API_TOKEN")).toHaveTextContent(
      "configured",
    );

    expect(screen.queryByTestId("admin-access-restricted")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-platform-only-hint")).not.toBeInTheDocument();
  });
});
