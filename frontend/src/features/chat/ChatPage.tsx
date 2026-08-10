import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConversation,
  listConversations,
  listMessages,
  postMessage,
  type RecallBundle,
} from "@/api/conversations";

export function ChatPage() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [lastRecall, setLastRecall] = useState<RecallBundle | null>(null);

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });

  const messagesQuery = useQuery({
    queryKey: ["conversations", activeId, "messages"],
    queryFn: () => listMessages(activeId as string),
    enabled: Boolean(activeId),
  });

  const createMutation = useMutation({
    mutationFn: () => createConversation({ title: "New conversation" }),
    onSuccess: async ({ id }) => {
      setActiveId(id);
      setLastRecall(null);
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const sendMutation = useMutation({
    mutationFn: (content: string) => postMessage(activeId as string, content),
    onSuccess: async (response) => {
      setLastRecall(response.recall);
      setDraft("");
      await queryClient.invalidateQueries({
        queryKey: ["conversations", activeId, "messages"],
      });
    },
  });

  return (
    <div className="flex flex-1 gap-4 p-6">
      <aside className="w-64 shrink-0 rounded-lg border border-slate-800 bg-leovee-panel p-3">
        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="mb-3 w-full rounded bg-leovee-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          New conversation
        </button>
        <ul className="space-y-1 text-sm">
          {conversationsQuery.data?.items.map((conversation) => (
            <li key={conversation.id}>
              <button
                type="button"
                onClick={() => {
                  setActiveId(conversation.id);
                  setLastRecall(null);
                }}
                className={`block w-full truncate rounded px-2 py-1.5 text-left ${
                  activeId === conversation.id
                    ? "bg-slate-800 text-white"
                    : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                {conversation.title}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex flex-1 flex-col rounded-lg border border-slate-800 bg-leovee-panel p-4">
        {!activeId && <p className="text-slate-400">Select or start a conversation.</p>}
        {activeId && (
          <>
            <div className="flex-1 space-y-3 overflow-auto" data-testid="message-list">
              {messagesQuery.data?.items.map((message) => (
                <div
                  key={message.id}
                  className={message.role === "user" ? "text-right" : "text-left"}
                >
                  <p
                    className={`inline-block max-w-lg rounded px-3 py-2 text-sm ${
                      message.role === "user"
                        ? "bg-leovee-accent text-white"
                        : "bg-slate-800 text-slate-100"
                    }`}
                  >
                    {message.content}
                  </p>
                </div>
              ))}
            </div>
            {lastRecall && (
              <div
                data-testid="recall-panel"
                className="mt-3 rounded border border-sky-800 bg-sky-950/40 p-3 text-xs text-sky-200"
              >
                <p className="font-semibold uppercase tracking-wide">
                  {lastRecall.label ?? "RECALL"} · {lastRecall.count} memories
                </p>
                {lastRecall.items && lastRecall.items.length > 0 && (
                  <ul className="mt-1 list-inside list-disc">
                    {lastRecall.items.slice(0, 5).map((item, index) => (
                      <li key={index}>{JSON.stringify(item)}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {sendMutation.isError && (
              <p className="mt-2 text-sm text-amber-400">
                {sendMutation.error instanceof Error
                  ? sendMutation.error.message
                  : "Could not send message."}
              </p>
            )}
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (draft.trim()) sendMutation.mutate(draft.trim());
              }}
              className="mt-3 flex gap-2"
            >
              <label htmlFor="chat-draft" className="sr-only">
                Message
              </label>
              <input
                id="chat-draft"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Ask about a symbol, setup, or your history…"
                className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
              />
              <button
                type="submit"
                disabled={sendMutation.isPending}
                className="rounded bg-leovee-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          </>
        )}
      </section>
    </div>
  );
}
