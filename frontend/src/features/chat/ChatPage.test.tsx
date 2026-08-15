import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { resetSheetForTests } from "@/api/sheetStore";
import { ChatPage } from "./ChatPage";

const postMessageStream = vi.fn();
const listMessages = vi.fn();
const listConversations = vi.fn();
const createConversation = vi.fn();

vi.mock("../../api/conversations", () => ({
  listMessages: (...args: unknown[]) => listMessages(...args),
  listConversations: (...args: unknown[]) => listConversations(...args),
  postMessageStream: (...args: unknown[]) => postMessageStream(...args),
  createConversation: (...args: unknown[]) => createConversation(...args),
}));

// The chart companion is mounted alongside the conversation — never
// conditionally, by design (its widget must never unmount when the
// sheet/pane toggles). These tests are about the conversation, not the
// chart, so its dependencies are stubbed the same way ChartCompanionPanel's
// own test suite stubs them: real network calls and a 27 MB vendored script
// tag have no place here.
vi.mock("@/api/markets", () => ({
  getCandles: vi.fn().mockResolvedValue({
    symbol: "XAUUSD",
    timeframe: "H1",
    workspace_id: "ws-1",
    candles: [],
  }),
}));
vi.mock("@/api/chart", () => ({
  listChartAnnotations: vi.fn().mockResolvedValue({ items: [] }),
}));
vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => ({ data: "ws-1" }),
}));
vi.mock("@/features/chart/useChartStream", () => ({
  useChartStream: () => undefined,
}));
vi.mock("@/chart/tradingview/TradingViewChart", () => ({
  TradingViewChart: () => <div data-testid="tradingview-chart" />,
}));

function renderPage(route = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LocaleProvider initialLocale="ar">
        <MemoryRouter initialEntries={[route]}>
          <ChatPage />
        </MemoryRouter>
      </LocaleProvider>
    </QueryClientProvider>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    resetSheetForTests();
    // The desktop chart-open preference and chat-width persist to
    // localStorage across real sessions on purpose — cleared here so one
    // test's deep link does not leak into the next test's initial render.
    window.localStorage.removeItem("leovee.chat-chart-open");
    window.localStorage.removeItem("leovee.chat-width");
    listMessages.mockReset();
    listConversations.mockReset();
    postMessageStream.mockReset();
    createConversation.mockReset();
    listConversations.mockResolvedValue({
      items: [{ id: "c1", title: "XAUUSD", symbol: "XAUUSD", mode: "CHAT", summary_text: null }],
    });
    listMessages.mockResolvedValue({ items: [], summary_text: null });
  });

  it("streams assistant tokens incrementally", async () => {
    postMessageStream.mockImplementation(
      async (
        _id: string,
        _content: string,
        handlers: {
          onToken: (t: string) => void;
          onDone: (p: { assistant_message_id: string; actions: unknown[] }) => void;
        },
      ) => {
        handlers.onToken("Hello ");
        handlers.onToken("world");
        handlers.onDone({ assistant_message_id: "a1", actions: [] });
      },
    );

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "XAUUSD" }));
    fireEvent.change(await screen.findByTestId("chat-draft-input"), { target: { value: "hi" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    await waitFor(() => {
      expect(postMessageStream).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("message-list")).toBeInTheDocument();
    });
  });

  it("the chart toggle opens the companion panel, closed by default", async () => {
    renderPage();

    const toggle = await screen.findByTestId("chat-chart-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-pressed", "true");
    // The chart's own controls are always mounted (never unmounted by the
    // sheet/pane toggle) — this is the same panel, now open.
    expect(screen.getByTestId("chart-symbol-input")).toBeInTheDocument();
  });

  it("a symbol deep link (from 'View chart' on a finished analysis) opens the chart automatically", async () => {
    renderPage("/?symbol=XAUUSD&timeframe=H1&chart=1");

    const toggle = await screen.findByTestId("chat-chart-toggle");
    await waitFor(() => expect(toggle).toHaveAttribute("aria-pressed", "true"));
  });
});
