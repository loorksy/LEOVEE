import { beforeEach, describe, expect, it } from "vitest";
import { clearTokens, getAccessToken, getRefreshToken, isAuthenticated, setTokens } from "./authStore";

describe("authStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("is unauthenticated with no stored tokens", () => {
    expect(isAuthenticated()).toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it("stores and retrieves tokens, then clears them", () => {
    setTokens({ access_token: "access-1", refresh_token: "refresh-1" });
    expect(getAccessToken()).toBe("access-1");
    expect(getRefreshToken()).toBe("refresh-1");
    expect(isAuthenticated()).toBe(true);

    clearTokens();
    expect(isAuthenticated()).toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it("dispatches leovee-auth-changed on token changes", () => {
    let fired = 0;
    const handler = () => {
      fired += 1;
    };
    window.addEventListener("leovee-auth-changed", handler);
    setTokens({ access_token: "a", refresh_token: "b" });
    clearTokens();
    window.removeEventListener("leovee-auth-changed", handler);
    expect(fired).toBe(2);
  });
});
