/**
 * The chat workspace — chat and chart are not two pages, they are one
 * surface, matching AiChart's console exactly: the chart is a bottom sheet
 * pulled up over the conversation below `xl` (1280px), and a resizable pane
 * beside it from `xl`. One control toggles both regimes; the chart node
 * (`ChartCompanionPanel`) is never unmounted by the toggle, only
 * repositioned with CSS, so drawings on it survive every open/close.
 */
import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, LineChart, Plus } from "lucide-react";
import { useSearchParams } from "react-router-dom";
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
import { useSheetSlot } from "@/hooks/useSheet";
import { useSheetGesture } from "@/hooks/useSheetGesture";
import { ChartCompanionPanel } from "@/features/chat/ChartCompanionPanel";

const CHAT_WIDTH_KEY = "leovee.chat-width";
const DESKTOP_CHART_KEY = "leovee.chat-chart-open";
const MIN_CHAT_WIDTH = 320;
const MAX_CHAT_WIDTH = 640;
const DEFAULT_CHAT_WIDTH = 420;

function clampChatWidth(width: number): number {
  return Math.min(MAX_CHAT_WIDTH, Math.max(MIN_CHAT_WIDTH, width));
}

function loadChatWidth(): number {
  if (typeof window === "undefined") return DEFAULT_CHAT_WIDTH;
  const raw = Number(window.localStorage.getItem(CHAT_WIDTH_KEY));
  return Number.isFinite(raw) && raw > 0 ? clampChatWidth(raw) : DEFAULT_CHAT_WIDTH;
}

function saveChatWidth(width: number): void {
  window.localStorage.setItem(CHAT_WIDTH_KEY, String(width));
}

function loadDesktopChartOpen(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(DESKTOP_CHART_KEY) === "1";
}

function saveDesktopChartOpen(open: boolean): void {
  window.localStorage.setItem(DESKTOP_CHART_KEY, open ? "1" : "0");
}

export function ChatPage() {
  const { t, dir } = useLocale();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
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

  // --- chart companion: sheet below xl, resizable pane from xl ------------
  const [chartSheetOpen, setChartSheetOpen] = useSheetSlot("chart");
  const [sheetExpanded, setSheetExpanded] = useState(false);
  useEffect(() => {
    if (!chartSheetOpen) setSheetExpanded(false);
  }, [chartSheetOpen]);
  const sheetPaneRef = useRef<HTMLDivElement>(null);
  const { handleProps: sheetHandleProps } = useSheetGesture({
    sheetRef: sheetPaneRef,
    onDismiss: () => setChartSheetOpen(false),
    expandable: true,
    expanded: sheetExpanded,
    onExpandedChange: setSheetExpanded,
  });

  const [desktopChartOpen, setDesktopChartOpen] = useState(false);
  useEffect(() => setDesktopChartOpen(loadDesktopChartOpen()), []);
  const applyDesktopChartOpen = useCallback((open: boolean) => {
    setDesktopChartOpen(open);
    saveDesktopChartOpen(open);
  }, []);

  const [chatWidth, setChatWidth] = useState(DEFAULT_CHAT_WIDTH);
  useEffect(() => setChatWidth(loadChatWidth()), []);

  // A symbol/timeframe/chart=1 arriving in the URL (from "View chart" on a
  // finished analysis) opens the companion in whichever regime is current —
  // a deep link that lands on a closed panel would look like the link failed.
  const openedFromLink = useRef(false);
  useEffect(() => {
    if (openedFromLink.current) return;
    const wantsChart =
      searchParams.get("chart") === "1" ||
      searchParams.has("symbol") ||
      searchParams.has("timeframe");
    if (!wantsChart) return;
    openedFromLink.current = true;
    setChartSheetOpen(true);
    applyDesktopChartOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const [isWide, setIsWide] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1280px)");
    const sync = () => setIsWide(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  const toggleChart = useCallback(() => {
    if (isWide) {
      applyDesktopChartOpen(!desktopChartOpen);
      return;
    }
    setChartSheetOpen(!chartSheetOpen);
  }, [isWide, desktopChartOpen, applyDesktopChartOpen, chartSheetOpen, setChartSheetOpen]);

  // Chat is the trailing column in LTR and the leading one in RTL — dragging
  // always widens toward the chart, whichever physical side that is.
  const startChatResize = (event: ReactPointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = chatWidth;
    const sign = dir === "rtl" ? 1 : -1;
    const onMove = (moveEvent: PointerEvent) =>
      setChatWidth(clampChatWidth(startWidth + sign * (startX - moveEvent.clientX)));
    const onUp = (upEvent: PointerEvent) => {
      saveChatWidth(clampChatWidth(startWidth + sign * (startX - upEvent.clientX)));
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const resizeChatWithKeyboard = (event: React.KeyboardEvent) => {
    let next: number | null = null;
    if (event.key === "ArrowLeft") next = chatWidth + (dir === "rtl" ? -24 : 24);
    if (event.key === "ArrowRight") next = chatWidth + (dir === "rtl" ? 24 : -24);
    if (event.key === "Home") next = MIN_CHAT_WIDTH;
    if (event.key === "End") next = MAX_CHAT_WIDTH;
    if (next == null) return;
    event.preventDefault();
    const clamped = clampChatWidth(next);
    setChatWidth(clamped);
    saveChatWidth(clamped);
  };

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

  const chartPaneClass = cn(
    "flex min-h-0 flex-col overflow-hidden bg-background",
    sheetExpanded ? "fixed inset-x-0 bottom-0 z-40 h-[100dvh]" : "fixed inset-x-0 bottom-0 z-40 h-[88dvh]",
    "rounded-t-xl border-t border-border shadow-2xl",
    "transition-[transform,height] duration-300 ease-out motion-reduce:transition-none",
    chartSheetOpen ? "translate-y-0" : "invisible translate-y-full",
    // From xl it is an ordinary pane again: no fixed positioning, no transform.
    "xl:visible xl:static xl:inset-auto xl:z-auto xl:h-auto xl:flex-1",
    "xl:translate-y-0 xl:rounded-none xl:border-t-0 xl:shadow-none xl:transition-none",
    desktopChartOpen ? "xl:flex" : "xl:hidden",
  );

  const chatPaneClass = cn(
    "flex min-h-0 w-full flex-col gap-4",
    desktopChartOpen ? "xl:w-[var(--chat-w)] xl:shrink-0" : "xl:w-full",
  );

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4"
      style={{ "--chat-w": `${chatWidth}px` } as React.CSSProperties}
    >
      <PageHeader
        title={t("nav.chat")}
        testId="chat-title"
        actions={
          <Button
            type="button"
            variant={desktopChartOpen || chartSheetOpen ? "secondary" : "outline"}
            size="sm"
            data-testid="chat-chart-toggle"
            aria-pressed={desktopChartOpen || chartSheetOpen}
            onClick={toggleChart}
          >
            <LineChart className="size-4" aria-hidden="true" />
            {t("chat.toggleChart")}
          </Button>
        }
      />
      {providersQuery.isSuccess && !llmConfigured && (
        <ProviderNotConfiguredBanner
          title={t("chat.error.llm")}
          credentials={llmCredentialNames()}
          testId="chat-llm-not-configured"
        />
      )}

      {/* Backdrop, below xl only — from xl the chart is a pane and has
          nothing to dismiss. */}
      {chartSheetOpen && (
        <button
          type="button"
          aria-label={t("chat.closeChart")}
          onClick={() => setChartSheetOpen(false)}
          className="fixed inset-0 z-30 bg-black/50 transition-opacity duration-250 xl:hidden motion-reduce:transition-none"
        />
      )}

      <div className="flex min-h-0 flex-1 gap-0 xl:gap-3">
        <div className={chatPaneClass}>
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
                                    (message.content_json?.artifacts as
                                      | ChatArtifact[]
                                      | undefined) ?? null
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
                      if (draft.trim() && !isStreaming && llmConfigured)
                        void sendStreaming(draft.trim());
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
                    <Button
                      type="submit"
                      data-testid="chat-send"
                      disabled={isStreaming || !llmConfigured}
                    >
                      {isStreaming ? t("chat.streaming") : t("chat.send")}
                    </Button>
                  </form>
                </>
              )}
            </Card>
          </div>
        </div>

        {/* Resize handle — desktop pane only. */}
        {desktopChartOpen && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={t("chat.resizeChart")}
            tabIndex={0}
            onPointerDown={startChatResize}
            onKeyDown={resizeChatWithKeyboard}
            data-testid="chat-resize-handle"
            className="hidden w-1 shrink-0 cursor-col-resize rounded-full bg-border transition-colors hover:bg-ring focus-visible:bg-ring focus-visible:outline-none xl:block"
          />
        )}

        <div ref={sheetPaneRef} data-testid="chart-companion" className={chartPaneClass}>
          <div
            {...sheetHandleProps}
            className="flex h-6 shrink-0 cursor-grab items-center justify-center xl:hidden"
            data-testid="chart-sheet-handle"
          >
            <span aria-hidden className="h-1 w-10 rounded-full bg-muted-foreground/40" />
          </div>
          <ChartCompanionPanel />
        </div>
      </div>
    </div>
  );
}
