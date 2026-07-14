"use client";

import { ArrowDown, Check, ChevronLeft, Send, Square, X } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AttachmentUploader } from "@/components/attachments/AttachmentUploader";
import { MessageAttachmentCapsules } from "@/components/attachments/MessageAttachmentCapsules";
import { AssistantMarkdown } from "@/components/persona-create/AssistantMarkdown";
import { Button } from "@/components/ui/button";
import { FloatingScrollButton } from "@/components/ui-patterns/FloatingScrollButton";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatAvatar } from "@/components/ui-patterns/ChatAvatar";
import { apiFetch } from "@/lib/api-client";
import { consumePersonaChatSse } from "@/lib/persona-chat-sse";
import { scrollScrollAreaViewportToBottom } from "@/lib/scroll-area-viewport";
import { generateUUID } from "@/lib/uuid";
import { useAttachmentBubblePreviews } from "@/hooks/use-attachment-bubble-previews";
import type { ChatMessage, PersonaConfirmGenerateResponse } from "@/types/persona";

const PERSONA_CONV_STORAGE_KEY = "xd.personaCreationConversationId";

export function PersonaCreateClient() {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [typingHintVisible, setTypingHintVisible] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [persistedId, setPersistedId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState("");
  const [draftTurnId, setDraftTurnId] = useState(() => generateUUID());
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [hadAttachmentUpload, setHadAttachmentUpload] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);
  const [leaveDestination, setLeaveDestination] = useState("/personas");
  const [showBackToLatest, setShowBackToLatest] = useState(false);

  useEffect(() => {
    let x = sessionStorage.getItem(PERSONA_CONV_STORAGE_KEY);
    if (!x) {
      x = generateUUID();
      sessionStorage.setItem(PERSONA_CONV_STORAGE_KEY, x);
    }
    setConversationId(x);
  }, []);

  const userMessageAttachmentIds = useMemo(
    () =>
      [...new Set(messages.flatMap((m) => (m.role === "user" ? m.attachment_ids ?? [] : [])))],
    [messages],
  );
  const attachmentPreviewById = useAttachmentBubblePreviews(userMessageAttachmentIds);

  const hasConfirmable = useMemo(
    () =>
      hadAttachmentUpload || messages.some((m) => m.role === "user" && m.content.trim()),
    [hadAttachmentUpload, messages],
  );

  const needsLeaveConfirm = useMemo(
    () => !persistedId && messages.length > 0,
    [persistedId, messages.length],
  );

  function requestLeave(dest: string): void {
    if (needsLeaveConfirm) {
      setLeaveDestination(dest);
      setLeaveDialogOpen(true);
      return;
    }
    router.push(dest);
  }

  function confirmLeave(): void {
    setLeaveDialogOpen(false);
    router.push(leaveDestination);
  }

  useLayoutEffect(() => {
    scrollScrollAreaViewportToBottom(bottomRef.current);
  }, [messages, typingHintVisible]);

  useEffect(() => {
    const candidate = bottomRef.current?.closest("[data-slot='scroll-area-viewport']");
    if (!(candidate instanceof HTMLElement)) return;
    const viewport = candidate;

    function onScroll(): void {
      setShowBackToLatest(viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight > 240);
    }

    onScroll();
    viewport.addEventListener("scroll", onScroll, { passive: true });
    return () => viewport.removeEventListener("scroll", onScroll);
  }, [messages.length]);

  useEffect(() => {
    if (!sending) {
      setTypingHintVisible(false);
      return;
    }
    const id = window.setTimeout(() => setTypingHintVisible(true), 800);
    return () => clearTimeout(id);
  }, [sending]);

  function stopGeneration(): void {
    abortControllerRef.current?.abort();
  }

  async function sendUserMessage(): Promise<void> {
    const text = draft.trim();
    if ((!text && attachmentIds.length === 0) || sending || !conversationId) return;

    const snapshot = messages;
    const idsThisRound = [...attachmentIds];
    const userTurn: ChatMessage = {
      role: "user",
      content: text,
      ...(idsThisRound.length > 0 ? { attachment_ids: idsThisRound } : {}),
    };
    const nextMessages: ChatMessage[] = [...snapshot, userTurn];

    setError(null);
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setMessages(nextMessages);
    setDraft("");
    setAttachmentIds([]);
    setSending(true);

    try {
      const res = await apiFetch("/api/personas/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          conversation_id: conversationId,
          draft_turn_id: draftTurnId,
          attachment_ids: idsThisRound,
        }),
        signal: ac.signal,
      });

      let accumulated = "";
      const final = await consumePersonaChatSse(res, (delta) => {
        accumulated += delta;
        setMessages([...nextMessages, { role: "assistant", content: accumulated }]);
      });

      setMessages([...nextMessages, { role: "assistant", content: final.assistant_message }]);
      if (idsThisRound.length > 0) {
        setHadAttachmentUpload(true);
      }
      setDraftTurnId(generateUUID());
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      if (aborted) {
        setMessages(nextMessages);
      } else {
        const msg = e instanceof Error ? e.message : "未知错误";
        setError(msg);
        setMessages(snapshot);
        setDraft(text);
        setAttachmentIds(idsThisRound);
      }
    } finally {
      abortControllerRef.current = null;
      setSending(false);
    }
  }

  async function confirmGenerate(): Promise<void> {
    if (!hasConfirmable || persistedId || !conversationId) return;
    setError(null);
    setConfirming(true);
    try {
      const res = await apiFetch("/api/personas/confirm-generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages, conversation_id: conversationId }),
      });

      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg =
          typeof detail?.detail === "string"
            ? detail.detail
            : `抽取或入库失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }

      const data = (await res.json()) as PersonaConfirmGenerateResponse;
      setPersistedId(data.id);
      router.push(`/personas/${data.id}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "未知错误";
      setError(msg);
    } finally {
      setConfirming(false);
    }
  }

  // 正在输入中指示器：sending=true 且助手还未开始回复时显示
  const showTypingDots =
    typingHintVisible &&
    (messages.length === 0 || messages[messages.length - 1]?.role === "user");

  return (
    <div className="h-dvh overflow-hidden bg-background text-foreground">
      <div className="mx-auto flex h-full min-h-0 w-full max-w-5xl flex-col md:px-6 md:py-6">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/30 shadow-lg shadow-foreground/5 ring-1 ring-border md:rounded-[2rem]">
      {leaveDialogOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[oklch(0.20_0.025_200/0.4)] p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setLeaveDialogOpen(false)}
        >
          <Card
            className="bg-background border-border max-w-md shadow-lg"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="leave-dialog-title"
            aria-describedby="leave-dialog-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <CardHeader>
              <CardTitle id="leave-dialog-title">尚未保存人设</CardTitle>
            </CardHeader>
            <div className="flex flex-col gap-4 p-6 pt-0">
              <p id="leave-dialog-desc" className="text-muted-foreground text-sm">
                您已与助手进行过对话，但还未点击「确认生成」将人设入库。此时离开将不会保留当前页面里的对话内容，确定要离开吗？
              </p>
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setLeaveDialogOpen(false)}>
                  <ChevronLeft className="size-4" aria-hidden />
                  留在本页
                </Button>
                <Button type="button" variant="destructive" onClick={confirmLeave}>
                  <X className="size-4" aria-hidden />
                  离开
                </Button>
              </div>
            </div>
          </Card>
        </div>
      ) : null}

          <header className="z-20 flex shrink-0 items-center justify-between border-b border-border/60 bg-card/85 px-3 py-3 backdrop-blur-xl md:px-5">
            <div className="flex min-w-0 items-center gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="shrink-0 rounded-full border-border bg-card px-3 py-2 text-foreground hover:bg-muted lg:hidden"
                onClick={() => requestLeave("/personas")}
              >
                <ChevronLeft className="size-4" aria-hidden />
                <span className="hidden sm:inline">人设库</span>
              </Button>
              <ChatAvatar name="人设创建助手" tone="assistant" imageSrc="/persona-assistant-avatar-v2.jpg" />
              <div className="min-w-0">
                <h1 className="truncate text-base font-semibold tracking-tight text-foreground md:text-lg">人设创建助手</h1>
                <p className="mt-1 truncate text-xs text-muted-foreground">通过对话生成一个可聊天的人设</p>
              </div>
            </div>
            {persistedId ? (
              <span className="rounded-full bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary ring-1 ring-primary/20">已生成，跳转中…</span>
            ) : (
              <Button
                variant="hero"
                className="rounded-full px-4"
                onClick={() => void confirmGenerate()}
                disabled={!hasConfirmable || sending || confirming || !conversationId}
              >
                <Check className="size-4" aria-hidden />
                {confirming ? "抽取中…" : "确认生成"}
              </Button>
            )}
          </header>

          {error ? (
            <div className="mx-4 mt-3 rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <main className="relative flex min-h-0 flex-1 flex-col">
            <FloatingScrollButton
              visible={showBackToLatest}
              label="回到最新内容"
              className="absolute right-4 bottom-24"
              onClick={() => {
                scrollScrollAreaViewportToBottom(bottomRef.current);
                setShowBackToLatest(false);
              }}
            >
              <ArrowDown className="size-4" aria-hidden />
              最新
            </FloatingScrollButton>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 px-4 py-5 md:px-8 md:py-7">
                {messages.length === 0 && !showTypingDots ? (
                  <div className="mx-auto mt-10 max-w-md rounded-3xl border border-dashed border-primary/30 bg-primary/5 px-5 py-4 text-center text-sm leading-relaxed text-muted-foreground shadow-sm">
                    先从一句话开始：你想模拟的对象大致是怎样的人？你们现在是什么关系阶段？
                  </div>
                ) : null}

                {messages.map((m, idx) => {
                  const isUser = m.role === "user";
                  const hasText = m.content.trim().length > 0;
                  const hasAttachments = isUser && m.attachment_ids && m.attachment_ids.length > 0;
                  return (
                    <div key={`${idx}-${m.role}`} className={isUser ? "flex justify-end" : "flex justify-start gap-2.5"}>
                      {!isUser ? <ChatAvatar name="人设创建助手" tone="assistant" size="sm" imageSrc="/persona-assistant-avatar-v2.jpg" /> : null}
                      <div className={isUser ? "flex max-w-[78%] flex-col items-end gap-2" : "flex max-w-[78%] flex-col items-start gap-2"}>
                        {hasText ? (
                          <div
                            className={
                              isUser
                                ? "rounded-[1.35rem] rounded-tr-md border border-primary/20 bg-primary/12 px-4 py-2.5 text-sm leading-relaxed text-foreground shadow-sm"
                                : "rounded-[1.35rem] rounded-tl-md border border-border/60 bg-card px-4 py-2.5 text-sm leading-relaxed text-foreground shadow-sm"
                            }
                          >
                            {!isUser ? <div className="mb-1 text-[11px] font-medium text-primary/60">人设创建助手</div> : null}
                            {m.role === "assistant" ? (
                              <AssistantMarkdown content={m.content} />
                            ) : (
                              <div className="whitespace-pre-wrap">{m.content}</div>
                            )}
                          </div>
                        ) : null}
                        {hasAttachments ? (
                          <MessageAttachmentCapsules
                            attachmentIds={m.attachment_ids ?? []}
                            previewById={attachmentPreviewById}
                            onImageLoad={() => scrollScrollAreaViewportToBottom(bottomRef.current)}
                          />
                        ) : null}
                      </div>
                    </div>
                  );
                })}

                {showTypingDots ? (
                  <div className="flex items-center gap-2.5" aria-live="polite">
                    <ChatAvatar name="人设创建助手" tone="assistant" size="sm" imageSrc="/persona-assistant-avatar-v2.jpg" />
                    <div className="rounded-full border border-border/60 bg-card px-4 py-2 text-sm text-muted-foreground shadow-sm">
                      助手正在整理信息…
                    </div>
                  </div>
                ) : null}

                <div ref={bottomRef} />
              </div>
            </ScrollArea>

            <div className="shrink-0 border-t border-border/60 bg-card/90 px-4 py-3 pb-[calc(env(safe-area-inset-bottom)+5.5rem)] backdrop-blur-xl md:px-6 lg:pb-3">
              <div className="flex flex-col gap-3">
                <AttachmentUploader
                  scene="persona_creation"
                  conversationId={conversationId}
                  draftTurnId={draftTurnId}
                  attachmentIds={attachmentIds}
                  onAttachmentIdsChange={setAttachmentIds}
                  disabled={confirming || !!persistedId || sending || !conversationId}
                />
                <div className="flex items-end gap-2 rounded-[1.5rem] border border-border bg-muted/50 p-2 shadow-inner">
                  <Textarea
                    className="max-h-32 min-h-11 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-[15px] leading-relaxed text-foreground shadow-none focus-visible:ring-0"
                    value={draft}
                    onChange={(e) => {
                      setDraft(e.target.value);
                    }}
                    placeholder="输入你的描述…"
                    rows={1}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        if (sending) return;
                        e.preventDefault();
                        void sendUserMessage();
                      }
                    }}
                    disabled={confirming || !!persistedId || !conversationId}
                  />
                  <Button
                    type="button"
                    size="icon-lg"
                    variant="outline"
                    className={`size-11 shrink-0 rounded-full border-0 shadow-sm transition-all ${sending ? "bg-muted text-muted-foreground" : "text-white hover:brightness-110 shadow-primary/20"}`}
                    style={sending ? undefined : { background: "var(--brand-gradient)" }}
                    aria-label={sending ? "终止等待" : "发送"}
                    disabled={
                      sending
                        ? false
                        : ((!draft.trim() && attachmentIds.length === 0) ||
                            confirming ||
                            !!persistedId ||
                            !conversationId)
                    }
                    onClick={() => {
                      if (sending) {
                        stopGeneration();
                      } else {
                        void sendUserMessage();
                      }
                    }}
                  >
                    {sending ? (
                      <Square className="size-3.5 fill-current" aria-hidden />
                    ) : (
                      <Send className="size-4" strokeWidth={2.25} aria-hidden />
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
