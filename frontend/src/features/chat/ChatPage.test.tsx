import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
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
    fireEvent.change(await screen.findByLabelText("Message"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(postMessageStream).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("message-list")).toBeInTheDocument();
    });
  });
});
