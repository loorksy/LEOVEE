import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { AlertsPage } from "./AlertsPage";
import * as alertsApi from "@/api/alerts";
import * as workspaceHook from "@/hooks/useWorkspaceId";
import * as notificationsStreamHook from "@/features/alerts/useNotificationsStream";

describe("AlertsPage", () => {
  it("lists alerts and fires the labeled UI test control", async () => {
    vi.spyOn(alertsApi, "listAlerts").mockResolvedValue({
      items: [
        {
          id: "alert-1",
          type: "PRICE",
          symbol_id: "sym-1",
          condition: { op: "gte", price: 1.1 },
          channels: { in_app: true },
          active: true,
          last_triggered_at: null,
        },
      ],
    });
    vi.spyOn(workspaceHook, "useWorkspaceId").mockReturnValue({
      data: "ws-1",
    } as ReturnType<typeof workspaceHook.useWorkspaceId>);
    vi.spyOn(notificationsStreamHook, "useNotificationsStream").mockImplementation(
      () => undefined,
    );
    const triggerSpy = vi
      .spyOn(alertsApi, "triggerAlert")
      .mockResolvedValue({ status: "triggered" });

    renderWithProviders(<AlertsPage />);

    expect(await screen.findByTestId("alert-alert-1")).toBeInTheDocument();

    expect(screen.getByText(/UI test control — not live evaluation/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/UI test price/i), {
      target: { value: "1.15" },
    });
    fireEvent.click(screen.getByRole("button", { name: /fire ui test \(not live\)/i }));

    await waitFor(() => expect(triggerSpy).toHaveBeenCalledWith("alert-1", 1.15));
  });

  it("creates an alert from the form", async () => {
    vi.spyOn(alertsApi, "listAlerts").mockResolvedValue({ items: [] });
    vi.spyOn(workspaceHook, "useWorkspaceId").mockReturnValue({
      data: "ws-1",
    } as ReturnType<typeof workspaceHook.useWorkspaceId>);
    vi.spyOn(notificationsStreamHook, "useNotificationsStream").mockImplementation(
      () => undefined,
    );
    const createSpy = vi.spyOn(alertsApi, "createAlert").mockResolvedValue({ id: "alert-2" });

    renderWithProviders(<AlertsPage />);

    expect(await screen.findByText(/no alerts yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /create alert/i }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith({
        type: "PRICE",
        symbol: "EURUSD",
        condition: { op: "gte", price: 1.1 },
        channels: { in_app: true },
      }),
    );
  });
});
