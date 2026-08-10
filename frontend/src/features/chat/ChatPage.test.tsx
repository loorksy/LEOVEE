import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { ChatPage } from "./ChatPage";
import * as conversationsApi from "@/api/conversations";

describe("ChatPage", () => {
  it("starts a conversation, sends a message, and shows the RECALL bundle", async () => {
    vi.spyOn(conversationsApi, "listConversations").mockResolvedValue({ items: [] });
    vi.spyOn(conversationsApi, "createConversation").mockResolvedValue({ id: "conv-1" });
    vi.spyOn(conversationsApi, "listMessages").mockResolvedValue({
      items: [],
      summary_text: null,
    });
    vi.spyOn(conversationsApi, "postMessage").mockResolvedValue({
      user_message_id: "m-user",
      assistant_message_id: "m-assistant",
      content: "EURUSD is showing a bullish structure break.",
      recall: {
        label: "HISTORICAL_MEMORY",
        symbol: "EURUSD",
        count: 2,
        items: [{ key: "eurusd.sweep.bias" }],
      },
      actions: [],
      summary_text: null,
    });

    renderWithProviders(<ChatPage />);

    fireEvent.click(await screen.findByRole("button", { name: /new conversation/i }));
    const input = await screen.findByLabelText(/message/i);
    fireEvent.change(input, { target: { value: "What is the setup on EURUSD?" } });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));

    const recallPanel = await screen.findByTestId("recall-panel");
    expect(recallPanel).toHaveTextContent("HISTORICAL_MEMORY");
    expect(recallPanel).toHaveTextContent("2 memories");
  });
});
