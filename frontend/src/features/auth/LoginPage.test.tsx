import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { LoginPage } from "./LoginPage";
import * as authApi from "@/api/auth";

describe("LoginPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("submits entered credentials to the auth API", async () => {
    const loginSpy = vi.spyOn(authApi, "login").mockResolvedValue({
      access_token: "a",
      refresh_token: "r",
      token_type: "bearer",
      expires_in: 900,
    });

    renderWithProviders(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "supersecret123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(loginSpy).toHaveBeenCalledWith("user@example.com", "supersecret123"),
    );
  });

  it("shows an error message when login fails", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(new Error("Invalid credentials"));

    renderWithProviders(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "wrongpass123" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
  });
});
