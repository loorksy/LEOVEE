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

    fireEvent.change(screen.getByTestId("login-email"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: "supersecret123" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() =>
      expect(loginSpy).toHaveBeenCalledWith("user@example.com", "supersecret123"),
    );
  });

  it("shows an error message when login fails", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(new Error("Invalid credentials"));

    renderWithProviders(<LoginPage />);

    fireEvent.change(screen.getByTestId("login-email"), {
      target: { value: "user@example.com" },
    });
    fireEvent.change(screen.getByTestId("login-password"), { target: { value: "wrongpass123" } });
    fireEvent.click(screen.getByTestId("login-submit"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
  });
});
