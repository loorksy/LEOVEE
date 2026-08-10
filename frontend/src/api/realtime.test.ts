import { afterEach, describe, expect, it, vi } from "vitest";
import { buildAuthenticatedStreamUrl, buildStreamUrl } from "./realtime";
import { clearTokens, setTokens } from "./authStore";

describe("buildStreamUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("builds a ws:// url from the current window origin when no API base is set", () => {
    const url = buildStreamUrl({
      token: "tok",
      symbols: ["EURUSD"],
      channels: ["candles", "annotations"],
      workspaceId: "ws-1",
    });
    expect(url.startsWith("ws://")).toBe(true);
    expect(url).toContain("/ws/v1/stream?");
    expect(url).toContain("token=tok");
    expect(url).toContain("symbols=EURUSD");
    expect(url).toContain("channels=candles%2Cannotations");
    expect(url).toContain("workspace_id=ws-1");
  });

  it("derives ws scheme from an https API base", () => {
    vi.stubEnv("VITE_API_URL", "https://api.leovee.example");
    const url = buildStreamUrl({ token: "tok" });
    expect(url.startsWith("wss://api.leovee.example")).toBe(true);
  });
});

describe("buildAuthenticatedStreamUrl", () => {
  afterEach(() => {
    clearTokens();
  });

  it("returns null when no token is stored", () => {
    expect(buildAuthenticatedStreamUrl({})).toBeNull();
  });

  it("uses the stored access token", () => {
    setTokens({ access_token: "stored-token", refresh_token: "r" });
    const url = buildAuthenticatedStreamUrl({ workspaceId: "ws-1" });
    expect(url).toContain("token=stored-token");
  });
});
