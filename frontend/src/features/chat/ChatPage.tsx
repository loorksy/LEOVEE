import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import {
  createConversation,
  listConversations,
  listMessages,
  postMessageStream,
  type RecallBundle,
} from "@/api/conversations";
import { getProvidersStatus } from "@/api/providers";
import { ApiError } from "@/api/httpClient";
import {
  ProviderNotConfiguredBanner,
  isLlmConfigured,
  llmCredentialNames,
} from "@/components/ProviderNotConfiguredBanner";
import { useLocale } from "@/i18n/context";
import { MessageContent } from "@/artifacts/MessageContent";
import type { ChatArtifact } from "@/artifacts/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";

export function ChatPage() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [lastRecall, setLastRecall] = useState<RecallBundle | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  // Mobile only: the conversation list and the active thread share one
  // column and only one shows at a time. sm:+ always shows both side by
  // side regardless of this flag — see the className ternaries below.
  const [mobileListOpen, setMobileListOpen] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const providersQuery = useQuery({
    queryKey: ["providers", "status"],
    queryFn: getProvidersStatus,
  });
  const llmConfigured = providersQuery.data ? isLlmConfigured(providersQuery.data) : true;

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });

  const messagesQuery = useQuery({
    queryKey: ["conversations", activeId, "messages"],
    queryFn: () => listMessages(activeId as string),
    enabled: Boolean(activeId),
  });

  const activeConversation = conversationsQuery.data?.items.find(
    (conversation) => conversation.id === activeId,
  );

  const createMutation = useMutation({
    mutationFn: () => createConversation({ title: t("chat.new") }),
    onSuccess: async ({ id }) => {
      setActiveId(id);
      setLastRecall(null);
      setStreamingText("");
      setStreamError(null);
      setMobileListOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const selectConversation = (id: string) => {
    setActiveId(id);
    setLastRecall(null);
    setStreamingText("");
    setStreamError(null);
    setMobileListOpen(false);
  };

  const sendStreaming = async (content: string) => {
    if (!activeId) return;
    if (!llmConfigured) {
      setStreamError(t("chat.error.notconfigured", { names: llmCredentialNames().join(", ") }));
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsStreaming(true);
    setStreamError(null);
    setStreamingText("");
    setDraft("");
    try {
      await postMessageStream(
        activeId,
        content,
        {
          onRecall: (recall) => setLastRecall(recall),
          onToken: (token) => setStreamingText((prev) => prev + token),
          onStreamReset: () => setStreamingText(""),
          onDone: async () => {
            setStreamingText("");
            await queryClient.invalidateQueries({
              queryKey: ["conversations", activeId, "messages"],
            });
          },
          onError: (info) => {
            setStreamError(info.message);
            setStreamingText("");
          },
        },
        controller.signal,
      );
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
      if (error instanceof ApiError && error.code === "provider_not_configured") {
        setStreamError(t("chat.error.notconfigured", { names: llmCredentialNames().join(", ") }));
      } else {
        setStreamError(error instanceof Error ? error.message : t("chat.error.send"));
      }
      setStreamingText("");
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <PageHeader title={t("nav.chat")} testId="chat-title" />
      {providersQuery.isSuccess && !llmConfigured && (
        <ProviderNotConfiguredBanner
          title={t("chat.error.llm")}
          credentials={llmCredentialNames()}
          testId="chat-llm-not-configured"
        />
      )}
      <div className="flex min-h-0 flex-1 gap-4">
        <Card
          className={cn(
            "w-full min-w-0 flex-col gap-3 p-3 sm:flex sm:w-64 sm:shrink-0",
            mobileListOpen ? "flex" : "hidden sm:flex",
          )}
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("chat.conversations")}
          </h2>
          <Button
            type="button"
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
            data-testid="chat-new-conversation"
            className="w-full"
          >
            <Plus className="size-4" aria-hidden="true" />
            {t("chat.new")}
          </Button>
          {conversationsQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-11 w-full sm:h-8" />
              <Skeleton className="h-11 w-full sm:h-8" />
              <Skeleton className="h-11 w-full sm:h-8" />
            </div>
          ) : conversationsQuery.data && conversationsQuery.data.items.length > 0 ? (
            <ul className="flex-1 space-y-1 overflow-y-auto text-sm">
              {conversationsQuery.data.items.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => selectConversation(conversation.id)}
                    className={cn(
                      "flex min-h-11 w-full items-center truncate rounded-md px-2 text-start text-sm transition-colors sm:min-h-0 sm:py-1.5",
                      activeId === conversation.id
                        ? "bg-muted font-medium text-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {conversation.title}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="flex-1 text-sm text-muted-foreground">{t("chat.noConversations")}</p>
          )}
        </Card>
        <Card
          className={cn(
            "min-w-0 flex-1 flex-col p-4",
            mobileListOpen ? "hidden sm:flex" : "flex",
          )}
        >
          {!activeId && <p className="text-muted-foreground">{t("chat.select")}</p>}
          {activeId && (
            <>
              <div className="mb-3 flex items-center gap-2 border-b border-border pb-3 sm:hidden">
                <IconButton
                  aria-label={t("chat.backToConversations")}
                  data-testid="chat-mobile-back"
                  onClick={() => setMobileListOpen(true)}
                >
                  <ArrowLeft className="size-5 rtl:rotate-180" aria-hidden="true" />
                </IconButton>
                <span className="truncate text-sm font-medium text-foreground">
                  {activeConversation?.title}
                </span>
              </div>
              <div className="flex-1 space-y-3 overflow-y-auto" data-testid="message-list">
                {messagesQuery.isLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-12 w-2/3" />
                    <Skeleton className="ms-auto h-12 w-1/2" />
                  </div>
                ) : (
                  <>
                    {messagesQuery.data?.items.map((message) => (
                      <div
                        key={message.id}
                        className={message.role === "user" ? "text-end" : "text-start"}
                      >
                        {message.role === "user" ? (
                          <p className="inline-block max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground sm:max-w-lg">
                            {message.content}
                          </p>
                        ) : (
                          <div className="inline-block max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground sm:max-w-2xl">
                            <MessageContent
                              content={message.content}
                              artifacts={
                                (message.content_json?.artifacts as ChatArtifact[] | undefined) ??
                                null
                              }
                            />
                          </div>
                        )}
                      </div>
                    ))}
                    {streamingText ? (
                      <div className="text-start" data-testid="streaming-assistant">
                        <div className="inline-block max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground sm:max-w-2xl">
                          <MessageContent content={streamingText} />
                          <span className="ms-1 inline-block h-3 w-1 animate-pulse bg-muted-foreground" />
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
              {lastRecall && (
                <div
                  data-testid="recall-panel"
                  className="mt-3 rounded-lg border border-info/30 bg-info/10 p-3 text-xs text-info"
                >
                  <p className="font-semibold uppercase tracking-wide">
                    {lastRecall.label ?? t("chat.recall")} ·{" "}
                    {t("chat.recall.count", { count: lastRecall.count })}
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
              {streamError && (
                <p className="mt-2 text-sm text-destructive" data-testid="chat-stream-error">
                  {streamError}
                </p>
              )}
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (draft.trim() && !isStreaming && llmConfigured) void sendStreaming(draft.trim());
                }}
                className="mt-3 flex flex-col gap-2 sm:flex-row"
              >
                <label htmlFor="chat-draft" className="sr-only">
                  {t("chat.message")}
                </label>
                <Input
                  id="chat-draft"
                  data-testid="chat-draft-input"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={t("chat.placeholder")}
                  className="flex-1"
                  disabled={isStreaming || !llmConfigured}
                />
                <Button type="submit" data-testid="chat-send" disabled={isStreaming || !llmConfigured}>
                  {isStreaming ? t("chat.streaming") : t("chat.send")}
                </Button>
              </form>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
