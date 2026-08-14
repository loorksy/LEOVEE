import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";
import { SettingsPage } from "./SettingsPage";

const getEntitlements = vi.fn();
vi.mock("../../api/billing", () => ({
  getEntitlements: (...args: unknown[]) => getEntitlements(...args),
}));

vi.mock("../../api/telegram", () => ({
  listLinks: () => Promise.resolve([]),
  createLinkCode: () => Promise.resolve({ code: "", expires_at: "", note: "" }),
  revokeLink: () => Promise.resolve(),
}));

// The shared harness, not a private one: it carries the locale provider, and a
// page-local wrapper is exactly how this test came to lack it.
function renderPage() {
  return renderWithProviders(<SettingsPage />);
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
    await waitFor(() =>
      expect(screen.getByTestId("plan-label")).toHaveTextContent("Pro (pro)"),
    );
    expect(screen.getByTestId("settings-broker-policy")).toBeInTheDocument();
  });
});
