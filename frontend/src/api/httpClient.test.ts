import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiError } from "./httpClient";
import { clearTokens, setTokens } from "./authStore";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("apiFetch", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("issues a GET without Authorization when no token is stored", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiFetch<{ ok: boolean }>("/api/v1/ping");

    expect(result).toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("attaches Authorization header when a token is stored", async () => {
    setTokens({ access_token: "tok-123", refresh_token: "r" });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/protected");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
  });

  it("serializes query params and JSON body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "1" }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/recommendations", {
      method: "POST",
      body: { symbol: "EURUSD" },
      query: { cards: true, unused: undefined },
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("?cards=true");
    expect(url).not.toContain("unused");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ symbol: "EURUSD" }));
  });

  it("throws ApiError with parsed detail on failure and clears tokens on 401", async () => {
    setTokens({ access_token: "expired", refresh_token: "r" });
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { detail: { message: "Not authenticated", code: "auth_required" } },
        { status: 401 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/v1/whoami")).rejects.toMatchObject({
      status: 401,
      message: "Not authenticated",
      code: "auth_required",
    });
  });

  it("re-exports a usable ApiError class", () => {
    const err = new ApiError(404, "missing");
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
  });

  afterEach(() => {
    clearTokens();
  });
});
