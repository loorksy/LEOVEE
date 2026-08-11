import { apiFetch } from "@/api/httpClient";

export type ConversationSummary = {
  id: string;
  title: string;
  symbol: string | null;
  mode: string;
  summary_text: string | null;
};

export type ConversationMessage = {
  id: string;
  role: "system" | "user" | "assistant" | string;
  content: string;
  content_json?: Record<string, unknown> | null;
  created_at: string;
};

export type RecallBundle = {
  label?: string;
  symbol?: string;
  count: number;
  items?: Array<Record<string, unknown>>;
};

export type PostMessageResponse = {
  user_message_id: string;
  assistant_message_id: string;
  content: string;
  recall: RecallBundle;
  actions: Array<Record<string, unknown>>;
  summary_text: string | null;
};

export async function listConversations(): Promise<{ items: ConversationSummary[] }> {
  return apiFetch<{ items: ConversationSummary[] }>("/api/v1/conversations");
}

export async function createConversation(params: {
  title?: string;
  symbol?: string | null;
  mode?: string;
}): Promise<{ id: string }> {
  return apiFetch<{ id: string }>("/api/v1/conversations", {
    method: "POST",
    body: {
      title: params.title ?? "New conversation",
      symbol: params.symbol ?? null,
      mode: params.mode ?? "CHAT",
    },
  });
}

export async function listMessages(
  conversationId: string,
): Promise<{ items: ConversationMessage[]; summary_text: string | null }> {
  return apiFetch(`/api/v1/conversations/${conversationId}/messages`);
}

export async function postMessage(
  conversationId: string,
  content: string,
): Promise<PostMessageResponse> {
  return apiFetch<PostMessageResponse>(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    body: { content, stream: false },
  });
}
