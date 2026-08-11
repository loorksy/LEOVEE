import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";

const getEntitlements = vi.fn();
vi.mock("../../api/billing", () => ({
  getEntitlements: (...args: unknown[]) => getEntitlements(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    getEntitlements.mockReset();
    getEntitlements.mockResolvedValue({
      plan_code: "pro",
      plan_name: "Pro",
      limits: { analyses_per_day: 100 },
      subscription_status: "active",
    });
  });

  it("shows entitlements", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Pro (pro)")).toBeInTheDocument());
    expect(screen.getByText(/OANDA execution remains disabled/i)).toBeInTheDocument();
  });
});
