import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useAuth } from "./useAuth";
import { clearTokens, setTokens } from "@/api/authStore";

describe("useAuth", () => {
  afterEach(() => {
    clearTokens();
  });

  it("reflects the current token state and updates on change", () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current.isAuthenticated).toBe(false);

    act(() => {
      setTokens({ access_token: "tok", refresh_token: "r" });
    });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      clearTokens();
    });
    expect(result.current.isAuthenticated).toBe(false);
  });
});
