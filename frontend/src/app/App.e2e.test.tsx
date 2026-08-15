/**
 * Batch 3 end-to-end path: log in → run analysis → see chart annotated →
 * recommendation → recalled memory.
 *
 * Playwright was not added for this batch: running a real browser here would
 * require downloading Chromium plus a live Postgres/Redis-backed API (OANDA
 * candles, LLM provider, migrations), which is slow and not reliably
 * available in this sandboxed CI environment. Instead this test drives the
 * real `<App />` component tree (real routes, real React Query, real
 * `apiFetch`/`fetch` call sites) against a mocked `fetch` + `WebSocket`,
 * exercising the same request/response contracts the browser would use.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "@/app/App";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { clearTokens } from "@/api/authStore";

// jsdom cannot load the vendored charting runtime, so the real chart engine
// cannot render here; stub it the same way ChartPage.test.tsx does and assert
// on the annotation-count readout instead of pixels.
vi.mock("@/chart", async () => {
  const actual = await vi.importActual<typeof import("@/chart")>("@/chart");
  return {
    ...actual,
    createChartEngine: vi.fn(() => ({
      setSymbol: vi.fn(),
      setTimeframe: vi.fn(),
      applyCandles: vi.fn(),
      applyCandlePatch: vi.fn(),
      applyAnnotations: vi.fn(),
      destroy: vi.fn(),
    })),
  };
});

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  close(): void {}
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const RECOMMENDATION_CARD = {
  id: "rec-1",
  symbol: "XAUUSD",
  direction: "BUY",
  status: "READY",
  confidence: 0.71,
  headline: "XAUUSD BUY",
  thesis: "Liquidity sweep then structure break, aligned with HTF bias.",
  badges: ["READY", "conf:71%"],
};

const CHART_ANNOTATION = {
  id: "ann-1",
  semantic_type: "DRAW_LEVEL",
  geometry: { anchors: [{ ts: "2024-01-01T12:00:00.000Z", price: 1.085 }] },
  style: { color: "#22c55e" },
  status: "ACTIVE",
  version: 1,
};

function routeFor(url: string): { pathname: string; search: URLSearchParams; method: string } {
  const parsed = new URL(url, "http://localhost");
  return { pathname: parsed.pathname, search: parsed.searchParams, method: "" };
}

describe("Batch 3 mocked end-to-end flow", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    window.history.pushState({}, "", "/");

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL, init: RequestInit = {}) => {
        const url = typeof input === "string" ? input : input.toString();
        const { pathname, search } = routeFor(url);
        const method = (init.method ?? "GET").toUpperCase();

        if (pathname === "/health/ready") {
          return jsonResponse({ status: "ok", checks: { database: { ok: true }, redis: { ok: true } } });
        }
        if (pathname === "/api/v1/auth/login" && method === "POST") {
          return jsonResponse({
            access_token: "test-access-token",
            refresh_token: "test-refresh-token",
            token_type: "bearer",
            expires_in: 900,
          });
        }
        if (pathname === "/api/v1/workspaces" && method === "GET") {
          return jsonResponse({
            items: [
              {
                id: "ws-1",
                tenant_id: "t-1",
                name: "Default",
                slug: "default",
                owner_user_id: "u-1",
                status: "ACTIVE",
                created_at: "2024-01-01T00:00:00.000Z",
                updated_at: "2024-01-01T00:00:00.000Z",
              },
            ],
          });
        }
        // The analysis form is gated on provider status; without this the
        // query fails, canRun stays false, and the form renders disabled.
        if (pathname === "/api/v1/providers/status" && method === "GET") {
          const ok = { configured: true, status: "ok" };
          return jsonResponse({
            finnhub: ok,
            oanda: { ...ok, environment: "practice" },
            anthropic: ok,
            openai: ok,
            openrouter: { ...ok, mode: "paid" },
          });
        }
        if (pathname === "/api/v1/analysis/run" && method === "POST") {
          return jsonResponse({
            agent_run_id: "run-1",
            workspace_id: "ws-1",
            symbol: "XAUUSD",
            timeframe: "H1",
            perceive: {},
            recall: { count: 2, items: [{ key: "xauusd.sweep.bias" }] },
            engines: { structure: { swept: true } },
            decision: { direction: "BUY", confidence: 0.71 },
            narrative: "Liquidity sweep then structure break, aligned with HTF bias.",
            as_of: "2024-01-01T12:00:00.000Z",
            recommendation_id: "rec-1",
            thesis_id: "thesis-1",
          });
        }
        if (pathname === "/api/v1/chart/semantic/build" && method === "POST") {
          return jsonResponse({
            model: {
              version: 1,
              operations: [
                {
                  semantic_type: "DRAW_LEVEL",
                  geometry: CHART_ANNOTATION.geometry,
                  style: CHART_ANNOTATION.style,
                },
              ],
            },
          });
        }
        if (pathname === "/api/v1/chart/semantic/persist" && method === "POST") {
          return jsonResponse({ ids: ["ann-1"], count: 1, version: 1 });
        }
        if (pathname === "/api/v1/markets/XAUUSD/candles" && method === "GET") {
          return jsonResponse({
            symbol: "XAUUSD",
            timeframe: "H1",
            workspace_id: "ws-1",
            candles: [
              {
                ts: "2024-01-01T12:00:00.000Z",
                open: 1.08,
                high: 1.09,
                low: 1.07,
                close: 1.085,
                volume: 120,
                complete: true,
              },
            ],
          });
        }
        if (pathname === "/api/v1/chart/annotations" && method === "GET") {
          return jsonResponse({ items: [CHART_ANNOTATION] });
        }
        if (pathname === "/api/v1/recommendations" && method === "GET") {
          expect(search.get("cards")).toBe("true");
          return jsonResponse({ items: [RECOMMENDATION_CARD] });
        }
        if (pathname === "/api/v1/conversations" && method === "GET") {
          return jsonResponse({ items: [] });
        }
        if (pathname === "/api/v1/conversations" && method === "POST") {
          return jsonResponse({ id: "conv-1" });
        }
        if (pathname === "/api/v1/conversations/conv-1/messages" && method === "GET") {
          return jsonResponse({ items: [], summary_text: null });
        }
        if (pathname === "/api/v1/conversations/conv-1/messages" && method === "POST") {
          const wantsStream =
            search.get("stream") === "true" ||
            (typeof init.body === "string" && init.body.includes('"stream":true'));
          if (wantsStream) {
            const events = [
              {
                event: "recall",
                label: "HISTORICAL_MEMORY",
                symbol: "XAUUSD",
                count: 2,
                items: [{ key: "xauusd.sweep.bias" }, { key: "xauusd.htf.trend" }],
              },
              { event: "user_message", id: "msg-user" },
              { event: "token", data: "XAUUSD is showing a bullish structure break, " },
              { event: "token", data: "consistent with your prior notes." },
              {
                event: "done",
                assistant_message_id: "msg-assistant",
                actions: [],
                provider: "test",
                via: "primary",
              },
            ];
            const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
            return new Response(body, {
              status: 200,
              headers: { "Content-Type": "text/event-stream" },
            });
          }
          return jsonResponse({
            user_message_id: "msg-user",
            assistant_message_id: "msg-assistant",
            content: "XAUUSD is showing a bullish structure break, consistent with your prior notes.",
            recall: {
              label: "HISTORICAL_MEMORY",
              symbol: "XAUUSD",
              count: 2,
              items: [{ key: "xauusd.sweep.bias" }, { key: "xauusd.htf.trend" }],
            },
            actions: [],
            summary_text: null,
          });
        }

        throw new Error(`Unhandled request in e2e test: ${method} ${pathname}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearTokens();
  });

  it("logs in, runs analysis, sees the annotated chart, a recommendation, and a recalled memory", async () => {
    // Same wrapping as main.tsx; the locale is pinned so the run does not
    // depend on the machine's navigator.language.
    render(
      <LocaleProvider initialLocale="ar">
        <App />
      </LocaleProvider>,
    );

    // Unauthenticated Home page redirects protected nav to /login.
    fireEvent.click(screen.getByTestId("nav-signin"));
    fireEvent.change(await screen.findByTestId("login-email"), {
      target: { value: "trader@example.com" },
    });
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: "correct-horse-battery" },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    // Back on the shell, now authenticated.
    await screen.findByTestId("home-title");

    // Run analysis. Elements outside this batch's converted files carry no
    // data-testid yet, so target them by stable DOM ids and structure — never
    // by display copy, which is locale-dependent.
    fireEvent.click(screen.getByTestId("nav-analysis"));
    await waitFor(() => expect(document.getElementById("analysis-symbol")).not.toBeNull());
    const symbolInput = document.getElementById("analysis-symbol") as HTMLInputElement;
    // The form stays disabled until provider status loads; clicking before then
    // silently does nothing.
    const runButton = symbolInput
      .closest("form")!
      .querySelector<HTMLButtonElement>('button[type="submit"]')!;
    await waitFor(() => expect(runButton).not.toBeDisabled());
    fireEvent.change(symbolInput, { target: { value: "XAUUSD" } });
    fireEvent.click(runButton);

    // The result heading carries the symbol — data from the mocked API, not UI copy.
    const resultHeading = await screen.findByRole("heading", { name: /XAUUSD/ });
    await screen.findByTestId("chart-status");

    // See the annotated chart — "view chart" is the first action in the result section.
    const resultSection = resultHeading.closest("section") as HTMLElement;
    fireEvent.click(within(resultSection).getAllByRole("button")[0]);
    expect(await screen.findByTestId("chart-container")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("annotation-count")).toHaveTextContent(/\b1\b/),
    );

    // See the recommendation (headline text comes from the mocked API, not UI copy).
    fireEvent.click(screen.getByTestId("nav-recommendations"));
    expect(await screen.findByText("XAUUSD BUY")).toBeInTheDocument();

    // See the recalled memory in chat. The "new conversation" button is the
    // page's own first button — scoped to app-main so shell chrome (menu
    // toggle, theme toggle, sign-out) is never a candidate.
    fireEvent.click(screen.getByTestId("nav-chat"));
    const newConversationButton = await waitFor(() => {
      const candidate = within(screen.getByTestId("app-main")).getAllByRole("button")[0];
      expect(candidate).toBeDefined();
      return candidate as HTMLElement;
    });
    fireEvent.click(newConversationButton);
    await waitFor(() => expect(document.getElementById("chat-draft")).not.toBeNull());
    const draft = document.getElementById("chat-draft") as HTMLInputElement;
    fireEvent.change(draft, { target: { value: "What's the current bias on XAUUSD?" } });
    fireEvent.click(
      draft.closest("form")!.querySelector<HTMLButtonElement>('button[type="submit"]')!,
    );

    const recallPanel = await screen.findByTestId("recall-panel");
    // Label and memory keys are mocked API data; the count assertion avoids the
    // translated "memories" copy.
    expect(within(recallPanel).getByText(/HISTORICAL_MEMORY/)).toBeInTheDocument();
    expect(recallPanel).toHaveTextContent(/\b2\b/);
    expect(within(recallPanel).getByText(/xauusd.sweep.bias/)).toBeInTheDocument();
  });
});
