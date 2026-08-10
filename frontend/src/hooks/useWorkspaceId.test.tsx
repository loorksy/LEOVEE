import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useWorkspaceId } from "./useWorkspaceId";
import * as workspacesApi from "@/api/workspaces";
import { clearTokens, setTokens } from "@/api/authStore";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useWorkspaceId", () => {
  afterEach(() => {
    clearTokens();
  });

  it("is disabled while unauthenticated", () => {
    const listSpy = vi.spyOn(workspacesApi, "listWorkspaces");
    const { result } = renderHook(() => useWorkspaceId(), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(listSpy).not.toHaveBeenCalled();
  });

  it("resolves the first workspace id once authenticated", async () => {
    setTokens({ access_token: "tok", refresh_token: "r" });
    vi.spyOn(workspacesApi, "listWorkspaces").mockResolvedValue({
      items: [
        {
          id: "ws-1",
          tenant_id: "t-1",
          name: "Default",
          slug: "default",
          owner_user_id: "u-1",
          status: "ACTIVE",
          created_at: "2024-01-01T00:00:00.000Z",
          updated_at: "2024-01-01T00:00:00.000Z",
        },
      ],
    });

    const { result } = renderHook(() => useWorkspaceId(), { wrapper });
    await waitFor(() => expect(result.current.data).toBe("ws-1"));
  });
});
