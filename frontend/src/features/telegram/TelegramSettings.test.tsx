import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { TelegramSettings } from "./TelegramSettings";
import * as telegramApi from "@/api/telegram";

describe("TelegramSettings", () => {
  it("shows a generated code once, with its expiry and the no-notifications promise", async () => {
    vi.spyOn(telegramApi, "listLinks").mockResolvedValue([]);
    vi.spyOn(telegramApi, "createLinkCode").mockResolvedValue({
      code: "ABCD2345",
      expires_at: new Date(Date.now() + 600_000).toISOString(),
      note: "الرمز صالح لعشر دقائق ويُستخدم مرة واحدة. لن يصلك شيء ما لم تسأل.",
    });

    renderWithProviders(<TelegramSettings />);
    fireEvent.click(screen.getByRole("button", { name: /توليد|Generate/i }));

    const panel = await screen.findByTestId("telegram-link-code");
    expect(panel).toHaveTextContent("ABCD2345");
    // The promise is restated at the moment of linking, not buried in a policy.
    expect(panel).toHaveTextContent(/لن يصلك شيء ما لم تسأل/);
  });

  it("lists a linked account and can unlink it", async () => {
    vi.spyOn(telegramApi, "listLinks").mockResolvedValue([
      {
        telegram_user_id: 4242,
        telegram_username: "trader",
        linked_at: new Date().toISOString(),
        last_message_at: null,
      },
    ]);
    const revoke = vi.spyOn(telegramApi, "revokeLink").mockResolvedValue(undefined);

    renderWithProviders(<TelegramSettings />);
    expect(await screen.findByTestId("telegram-link-4242")).toHaveTextContent("@trader");

    // Scoped to the row rather than matched by label: the page has two buttons
    // and an Arabic label match is one diacritic away from finding the wrong one.
    const row = within(screen.getByTestId("telegram-link-4242"));
    fireEvent.click(row.getByRole("button"));
    await waitFor(() => expect(revoke.mock.calls[0]?.[0]).toBe(4242));
  });

  it("says plainly when nothing is linked", async () => {
    vi.spyOn(telegramApi, "listLinks").mockResolvedValue([]);
    renderWithProviders(<TelegramSettings />);
    expect(await screen.findByText(/لا يوجد حساب مربوط|No account linked/i)).toBeInTheDocument();
  });
});
