import { apiUrl } from "@/api/config";
import { clearTokens, getAccessToken } from "@/api/authStore";
import { ApiError, apiFetch } from "@/api/httpClient";
import { getWorkspaceId } from "@/api/workspaceStore";

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

export type ChatStreamHandlers = {
  onRecall?: (recall: RecallBundle) => void;
  onToken?: (token: string) => void;
  onStreamReset?: (info: { reason: string; message?: string }) => void;
  onDone?: (info: {
    assistant_message_id: string;
    actions: Array<Record<string, unknown>>;
  }) => void;
  onError?: (info: { message: string; code?: string }) => void;
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

/** Provider-native SSE streaming — tokens arrive as the model produces them. */
export async function postMessageStream(
  conversationId: string,
  content: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const workspaceId = getWorkspaceId();
  if (workspaceId) headers["X-Workspace-Id"] = workspaceId;

  const response = await fetch(
    `${apiUrl(`/api/v1/conversations/${conversationId}/messages`)}?stream=true`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ content, stream: true }),
      signal,
    },
  );

  if (!response.ok) {
    if (response.status === 401) clearTokens();
    let message = response.statusText;
    let code: string | undefined;
    try {
      const data = (await response.json()) as {
        detail?: string | { message?: string; code?: string };
      };
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (data.detail && typeof data.detail === "object") {
        message = data.detail.message ?? message;
        code = data.detail.code;
      }
    } catch {
      // ignore
    }
    throw new ApiError(response.status, message, code);
  }

  if (!response.body) {
    throw new ApiError(500, "Streaming response body missing");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (raw: string) => {
    const line = raw.trim();
    if (!line.startsWith("data:")) return;
    const payload = line.slice(5).trim();
    if (!payload) return;
    const event = JSON.parse(payload) as Record<string, unknown>;
    const kind = String(event.event ?? "");
    if (kind === "recall") {
      handlers.onRecall?.({
        label: event.label as string | undefined,
        symbol: event.symbol as string | undefined,
        count: Number(event.count ?? 0),
        items: (event.items as Array<Record<string, unknown>>) ?? [],
      });
      return;
    }
    if (kind === "token") {
      handlers.onToken?.(String(event.data ?? ""));
      return;
    }
    if (kind === "stream_reset") {
      handlers.onStreamReset?.({
        reason: String(event.reason ?? "reset"),
        message: event.message ? String(event.message) : undefined,
      });
      return;
    }
    if (kind === "done") {
      handlers.onDone?.({
        assistant_message_id: String(event.assistant_message_id ?? ""),
        actions: (event.actions as Array<Record<string, unknown>>) ?? [],
      });
      return;
    }
    if (kind === "error") {
      handlers.onError?.({
        message: String(event.message ?? "stream error"),
        code: event.code ? String(event.code) : undefined,
      });
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      dispatch(part);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}
