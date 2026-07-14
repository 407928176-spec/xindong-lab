"use client";

import { ArrowDown, ChevronLeft, FileText, HeartHandshake, Send, Trash2 } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AttachmentUploader } from "@/components/attachments/AttachmentUploader";
import { MessageAttachmentCapsules } from "@/components/attachments/MessageAttachmentCapsules";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { FloatingScrollButton } from "@/components/ui-patterns/FloatingScrollButton";
import { WebSearchBadge } from "@/components/ui-patterns/WebSearchBadge";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { consumeCharacterChatSse } from "@/lib/character-chat-sse";
import { apiFetch } from "@/lib/api-client";
import { getEndingDisplay } from "@/lib/ending-display";
import { cn } from "@/lib/utils";
import { useAttachmentBubblePreviews } from "@/hooks/use-attachment-bubble-previews";
import { getScrollAreaViewport, scrollScrollAreaViewportToBottom } from "@/lib/scroll-area-viewport";
import {
  clearPendingChat,
  clearPendingPreview,
  getPendingChat,
  isActiveChatPage,
  notifyCharactersChanged,
  registerActiveChatPage,
  setPendingChat,
  setPendingPreview,
} from "@/lib/character-chat-pending";
import { clearDraft as clearDraftStorage, getDraft as getDraftStorage, setDraft as setDraftStorage } from "@/lib/character-chat-draft";
import { generateUUID } from "@/lib/uuid";
import type { CharacterChatResponse, CharacterDetailResponse, CharacterMessageItem } from "@/types/character";

type CharacterEnding = NonNullable<CharacterDetailResponse["ending"]>;

interface DraftSnapshot {
  draft: string;
  attachmentIds: string[];
  draftTurnId: string;
}

interface CharacterChatClientProps {
  characterId: string;
  variant?: "page" | "embedded";
  returnHref?: string;
  returnLabel?: string;
}

const TYPING_HINT_DELAY_MS = 1000;
const NEAR_BOTTOM_THRESHOLD_PX = 80;
const ENDING_NOTICE_DELAY_MS = 900;

export function CharacterChatClient({
  characterId,
  variant = "page",
  returnHref = "/",
  returnLabel = "对话列表",
}: CharacterChatClientProps) {
  const router = useRouter();
  const [detail, setDetail] = useState<CharacterDetailResponse | null>(null);
  const [messages, setMessages] = useState<CharacterMessageItem[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [typingHintVisible, setTypingHintVisible] = useState(false);
  const [endingData, setEndingData] = useState<{ result: string; evaluation: string; user_review?: string | null } | null>(null);
  const [endingPending, setEndingPending] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [endingNoticeVisible, setEndingNoticeVisible] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const draftRef = useRef("");
  const abortControllerRef = useRef<AbortController | null>(null);
  const endingNoticeTimerRef = useRef<number | null>(null);
  const activeCharacterIdRef = useRef(characterId);
  const draftCacheRef = useRef(new Map<string, DraftSnapshot>());
  const hydratedDraftCharacterIdRef = useRef<string | null>(null);
  const requestSeqRef = useRef(0);
  const [draftTurnId, setDraftTurnId] = useState(() => generateUUID());
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const userMessageAttachmentIds = useMemo(
    () =>
      [...new Set(messages.flatMap((m) => (m.role === "user" ? m.attachment_ids ?? [] : [])))],
    [messages],
  );
  const attachmentPreviewById = useAttachmentBubblePreviews(userMessageAttachmentIds);
  const scrollBehaviorAfterMessagesRef = useRef<"snap" | "preserve">("snap");
  // 检测组件是否仍挂载（避免卸载后的 state 更新）
  const mountedRef = useRef(true);
  // 用户已看到结局，离开聊天时需要 acknowledge-ending 的标记
  const shouldAckOnLeaveRef = useRef(false);

  draftRef.current = draft;
  activeCharacterIdRef.current = characterId;

  useEffect(() => {
    const previousId = hydratedDraftCharacterIdRef.current;
    if (previousId !== characterId) {
      if (previousId !== null) {
        // 切角色时把当前 draft 落到内存缓存与 localStorage，便于下次回到该角色时恢复
        draftCacheRef.current.set(previousId, { draft, attachmentIds, draftTurnId });
        setDraftStorage(previousId, draft);
      }
      const cached = draftCacheRef.current.get(characterId);
      const stored = cached?.draft ?? getDraftStorage(characterId);
      setDraft(stored);
      setAttachmentIds(cached?.attachmentIds ?? []);
      setDraftTurnId(cached?.draftTurnId ?? generateUUID());
      hydratedDraftCharacterIdRef.current = characterId;
    }
  }, [attachmentIds, characterId, draft, draftTurnId]);

  // 草稿落地：仅在组件卸载时写入 localStorage（切角色已在上方 effect 处理）
  // 不在每次按键时写入，避免列表页实时显示草稿预览
  useEffect(() => {
    return () => {
      const id = activeCharacterIdRef.current;
      const currentDraft = draftRef.current;
      if (id && hydratedDraftCharacterIdRef.current === id) {
        setDraftStorage(id, currentDraft);
      }
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (endingNoticeTimerRef.current !== null) {
        window.clearTimeout(endingNoticeTimerRef.current);
      }
    };
  }, []);

  // 注册当前聊天为活跃状态：移动独立页和桌面右侧嵌入态都不应产生未读标记。
  useEffect(() => {
    return registerActiveChatPage(characterId);
  }, [characterId]);

  // 用户离开聊天（切角色或路由离开）时才 acknowledge-ending，避免桌面端结局卡片在用户阅读时当场消失
  useEffect(() => {
    const id = characterId;
    return () => {
      if (!shouldAckOnLeaveRef.current) return;
      shouldAckOnLeaveRef.current = false;
      void apiFetch(`/api/characters/${id}/acknowledge-ending`, { method: "POST" })
        .then(() => notifyCharactersChanged(id))
        .catch(() => {});
    };
  }, [characterId]);

  // 从 localStorage 恢复终局数据（用户离开后重新进入时可见）
  useEffect(() => {
    try {
      const stored = localStorage.getItem(`xd.endingData.${characterId}`);
      if (stored) setEndingData(JSON.parse(stored) as { result: string; evaluation: string; user_review?: string | null });
    } catch {}
  }, [characterId]);

  const scrollViewportToBottom = (): boolean => scrollScrollAreaViewportToBottom(bottomRef.current);

  const returnToList = useCallback((): void => {
    router.push(returnHref);
  }, [returnHref, router]);

  async function deleteCharacter(): Promise<void> {
    setDeleteLoading(true);
    try {
      const res = await apiFetch(`/api/characters/${characterId}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg = typeof body?.detail === "string" ? body.detail : `移入回收站失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }
      notifyCharactersChanged(characterId);
      if (variant !== "embedded") router.push(returnHref);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setDeleteLoading(false);
      setDeleteConfirmOpen(false);
    }
  }

  const revealEnding = useCallback(
    (ending: CharacterEnding) => {
      if (endingNoticeTimerRef.current !== null) {
        window.clearTimeout(endingNoticeTimerRef.current);
      }
      setEndingNoticeVisible(true);
      endingNoticeTimerRef.current = window.setTimeout(() => {
        endingNoticeTimerRef.current = null;
        if (!mountedRef.current || activeCharacterIdRef.current !== characterId) return;
        setEndingData(ending);
        localStorage.setItem(`xd.endingData.${characterId}`, JSON.stringify(ending));
        setEndingNoticeVisible(false);
        // 不在此处立即 acknowledge：等用户离开聊天页时才归档，避免桌面端卡片在用户阅读结局时当场消失
        shouldAckOnLeaveRef.current = true;
      }, ENDING_NOTICE_DELAY_MS);
    },
    [characterId],
  );

  const loadDetail = useCallback(async (): Promise<void> => {
    const loadingCharacterId = characterId;
    const shouldApplyLoadedDetail = (): boolean => mountedRef.current && activeCharacterIdRef.current === loadingCharacterId;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/characters/${loadingCharacterId}`, { method: "GET" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg =
          typeof body?.detail === "string" ? body.detail : `加载失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }
      const data = (await res.json()) as CharacterDetailResponse;
      if (!shouldApplyLoadedDetail()) return;
      scrollBehaviorAfterMessagesRef.current = "snap";
      setDetail(data);
      if (data.ending) {
        setEndingData(data.ending);
        localStorage.setItem(`xd.endingData.${loadingCharacterId}`, JSON.stringify(data.ending));
        shouldAckOnLeaveRef.current = true;
        clearDraftStorage(loadingCharacterId);
      } else {
        try {
          const stored = localStorage.getItem(`xd.endingData.${loadingCharacterId}`);
          setEndingData(stored ? (JSON.parse(stored) as { result: string; evaluation: string; user_review?: string | null }) : null);
        } catch {
          setEndingData(null);
        }
      }

      const pending = getPendingChat(loadingCharacterId);
      if (endingNoticeTimerRef.current !== null) {
        window.clearTimeout(endingNoticeTimerRef.current);
        endingNoticeTimerRef.current = null;
      }
      setEndingNoticeVisible(false);

      if (pending) {
        // 存在进行中的请求：展示 DB 消息 + 乐观用户消息，并订阅 promise
        const optimisticMsg: CharacterMessageItem = {
          id: pending.userTempId,
          role: "user",
          content: pending.userContent,
          round_number: 0,
          created_at: new Date().toISOString(),
          attachment_ids: pending.attachmentIds,
        };
        setMessages([...data.messages, optimisticMsg]);
        setSending(true); // 触发「对方正在输入中……」倒计时

        pending.promise
          .then((response) => {
            clearPendingChat(loadingCharacterId);
            if (!shouldApplyLoadedDetail()) return;
            scrollBehaviorAfterMessagesRef.current = "snap";
            setDetail((d) => (d ? { ...d, heartbeat_score: response.heartbeat_score } : d));
            setMessages((prev) => {
              const stripped = prev.filter((m) => m.id !== pending.userTempId);
              const existingIds = new Set(stripped.map((m) => m.id));
              const toAdd = [response.user_message, response.assistant_message_item].filter(
                (m) => !existingIds.has(m.id),
              );
              return [...stripped, ...toAdd];
            });
            setDraftTurnId(generateUUID());
            setSending(false);
            if (response.ending) {
              revealEnding(response.ending);
            } else {
              notifyCharactersChanged(loadingCharacterId);
            }
          })
          .catch((e: unknown) => {
            clearPendingChat(loadingCharacterId);
            if (!shouldApplyLoadedDetail()) return;
            setSending(false);
            const aborted = e instanceof DOMException && e.name === "AbortError";
            if (!aborted) setError("发送失败，消息可能未送达");
          });
      } else {
        setMessages(data.messages);
        // 用户重新进入对话页，清除未读提醒
        localStorage.removeItem(`xd.unreadReply.${loadingCharacterId}`);
        window.dispatchEvent(new CustomEvent("xd:unread-changed"));
      }
    } catch (e) {
      if (!shouldApplyLoadedDetail()) return;
      setDetail(null);
      setMessages([]);
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      if (shouldApplyLoadedDetail()) setLoading(false);
    }
  }, [characterId, revealEnding]);

  useEffect(() => {
    setSending(false);
    setTypingHintVisible(false);
    setEndingPending(false);
    setEndingNoticeVisible(false);
    abortControllerRef.current = null;
    requestSeqRef.current += 1;
    void loadDetail();
  }, [characterId, loadDetail]);

  const [assistantUnreadBump, setAssistantUnreadBump] = useState(false);
  const [showBackToLatest, setShowBackToLatest] = useState(false);

  useLayoutEffect(() => {
    if (loading || messages.length === 0) return;

    const mode = scrollBehaviorAfterMessagesRef.current;

    if (mode === "snap") {
      scrollViewportToBottom();
      setAssistantUnreadBump(false);
    } else {
      const lastRole = messages[messages.length - 1]?.role;
      setAssistantUnreadBump(lastRole === "character");
    }

    scrollBehaviorAfterMessagesRef.current = "snap";
  }, [loading, messages]);

  useEffect(() => {
    const viewport = getScrollAreaViewport(bottomRef.current);
    if (!viewport) return;
    let raf = 0;
    const vp = viewport;

    function onViewportScroll(): void {
      const d = vp.scrollHeight - vp.scrollTop - vp.clientHeight;
      setShowBackToLatest(d > 240);
      if (d <= NEAR_BOTTOM_THRESHOLD_PX) {
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => setAssistantUnreadBump(false));
      }
    }

    viewport.addEventListener("scroll", onViewportScroll, { passive: true });
    return () => {
      viewport.removeEventListener("scroll", onViewportScroll);
      cancelAnimationFrame(raf);
    };
  }, [messages]);

  useEffect(() => {
    if (!sending) {
      setTypingHintVisible(false);
      return;
    }
    const id = window.setTimeout(() => setTypingHintVisible(true), TYPING_HINT_DELAY_MS);
    return () => {
      clearTimeout(id);
    };
  }, [sending]);

  async function sendMessage(): Promise<void> {
    const text = draft.trim();
    if ((!text && attachmentIds.length === 0) || !detail) return;
    if (sending) return;
    if (detail.status === "ended" || endingData) return;

    const ts = Date.now();
    const requestCharacterId = characterId;
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    const shouldApplyToCurrentView = (): boolean =>
      mountedRef.current && activeCharacterIdRef.current === requestCharacterId && requestSeqRef.current === requestSeq;
    const userTempId = `local-user-${ts}`;
    const assistantTempId = `local-assistant-${ts}`;
    const idsSnapshot = [...attachmentIds];
    const turnSnapshot = draftTurnId;
    const optimisticUser: CharacterMessageItem = {
      id: userTempId,
      role: "user",
      content: text,
      round_number: 0,
      created_at: new Date().toISOString(),
      attachment_ids: idsSnapshot,
    };

    const snapshot = messages.slice();
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setError(null);
    setEndingNoticeVisible(false);
    setSending(true);
    setDraft("");
    setAttachmentIds([]);
    scrollBehaviorAfterMessagesRef.current = "snap";
    setMessages((prev) => [...prev, optimisticUser]);

    const fetchPromise: Promise<CharacterChatResponse> = (async (): Promise<CharacterChatResponse> => {
      const res = await apiFetch(`/api/characters/${characterId}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: text,
          attachment_ids: idsSnapshot,
          draft_turn_id: turnSnapshot,
        }),
        signal: ac.signal,
      });

      return consumeCharacterChatSse(res, {
        onAssistantDone: (assistantText) => {
          setPendingPreview(requestCharacterId, assistantText, Date.now());
          notifyCharactersChanged(requestCharacterId);
          if (!isActiveChatPage(requestCharacterId)) {
            localStorage.setItem(`xd.unreadReply.${requestCharacterId}`, "1");
            window.dispatchEvent(new CustomEvent("xd:unread-changed"));
          }
          if (!shouldApplyToCurrentView()) return;
          setTypingHintVisible(false);
          setMessages((prev) => {
            const others = prev.filter((m) => m.id !== assistantTempId);
            const assistantDraft: CharacterMessageItem = {
              id: assistantTempId,
              role: "character",
              content: assistantText,
              display_text: assistantText,
              round_number: 0,
              created_at: new Date().toISOString(),
            };
            return [...others, assistantDraft];
          });
        },
        onEndingPending: () => {
          if (!shouldApplyToCurrentView()) return;
          setEndingPending(true);
          setSending(false);
          setEndingNoticeVisible(true);
          // 终局确认时立即清掉草稿，避免落幕后角色卡片还显示草稿内容
          setDraft("");
          clearDraftStorage(requestCharacterId);
        },
      });
    })();

    setPendingChat(characterId, {
      userTempId,
      userContent: text,
      attachmentIds: idsSnapshot,
      promise: fetchPromise,
    });

    setPendingPreview(characterId, text, ts);
    notifyCharactersChanged(characterId);

    fetchPromise.then(
      () => {
        clearPendingPreview(characterId);
        notifyCharactersChanged(characterId);
      },
      () => { clearPendingPreview(characterId); },
    );

    let succeeded = false;
    try {
      const data = await fetchPromise;
      succeeded = true;

      if (shouldApplyToCurrentView()) {
        const vpEarly = getScrollAreaViewport(bottomRef.current);
        const dist =
          vpEarly !== null ? vpEarly.scrollHeight - vpEarly.scrollTop - vpEarly.clientHeight : null;
        const nearBottom =
          dist === null || dist < NEAR_BOTTOM_THRESHOLD_PX;
        scrollBehaviorAfterMessagesRef.current = nearBottom ? "snap" : "preserve";

        setDetail((d) => (d ? { ...d, heartbeat_score: data.heartbeat_score } : d));
        setMessages((prev) => {
          const stripped = prev.filter((m) => m.id !== userTempId && m.id !== assistantTempId);
          const existingIds = new Set(stripped.map((m) => m.id));
          const toAdd = [data.user_message, data.assistant_message_item].filter(
            (m) => !existingIds.has(m.id),
          );
          return [...stripped, ...toAdd];
        });
        setDraftTurnId(generateUUID());

        if (data.ending) {
          revealEnding(data.ending);
        } else {
          setEndingPending(false);
        }
      }

      notifyCharactersChanged(characterId);
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === "AbortError";
      clearPendingPreview(characterId);
      if (!aborted && shouldApplyToCurrentView()) {
        setMessages(snapshot);
        setDraft(text);
        setAttachmentIds(idsSnapshot);
        setEndingPending(false);
        setEndingNoticeVisible(false);
        setError(e instanceof Error ? e.message : "未知错误");
      }
    } finally {
      if (shouldApplyToCurrentView()) {
        abortControllerRef.current = null;
        setSending(false);
        if (!succeeded) setEndingPending(false);
      }
      clearPendingChat(characterId);
      if (succeeded) {
        notifyCharactersChanged(characterId);
      }
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <p className="text-muted-foreground text-sm">加载中…</p>
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <div className="bg-destructive/10 text-destructive rounded-lg border border-destructive/20 px-3 py-2 text-sm">
          {error}
        </div>
        <Button type="button" variant="outline" onClick={returnToList}>
          返回{returnLabel}
        </Button>
      </div>
    );
  }

  if (!detail) {
    return null;
  }

  const isEnded = detail.status === "ended" || endingData !== null;
  // textareaDisabled：结局/结算中时整体锁死；sending 时允许提前打字，发送按钮另行控制。
  const textareaDisabled = endingPending || isEnded || !detail;
  const sendDisabled = textareaDisabled || sending || (!draft.trim() && attachmentIds.length === 0);
  const relationshipStatus = isEnded ? "已落幕" : endingPending ? "结算中" : null;
  const isEmbedded = variant === "embedded";
  const endingDisplay = getEndingDisplay(endingData?.result);

  return (
    <>
    <div className={isEmbedded ? "h-full min-h-0 bg-app/80 text-foreground" : "h-dvh overflow-hidden bg-background text-foreground"}>
      <div className={isEmbedded ? "flex h-full min-h-0 w-full flex-col" : "mx-auto flex h-full min-h-0 w-full max-w-5xl flex-col md:px-6 md:py-6"}>
        <div className={isEmbedded ? "flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/30" : "flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/30 shadow-lg shadow-foreground/5 ring-1 ring-border md:rounded-[2rem]"}>
          <header className="z-20 flex shrink-0 items-center justify-between border-b border-border/60 bg-card/85 px-3 py-3 backdrop-blur-xl md:px-5">
            <div className="flex min-w-0 items-center gap-3">
              {!isEmbedded ? (
                <button
                  type="button"
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-card px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted lg:hidden"
                  aria-label={`返回${returnLabel}`}
                  onClick={returnToList}
                >
                  <ChevronLeft className="size-4" aria-hidden />
                  <span className="hidden sm:inline">{returnLabel}</span>
                </button>
              ) : null}
              <div
                className="relative flex size-11 shrink-0 items-center justify-center rounded-2xl font-heading text-sm font-semibold text-white shadow-sm shadow-primary/20 ring-1 ring-white/30"
                style={{ background: "var(--brand-gradient)" }}
              >
                {detail.display_name.slice(0, 1) || "心"}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="truncate font-heading text-base font-semibold tracking-tight text-foreground md:text-lg">{detail.display_name}</h1>
                  {relationshipStatus ? (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground ring-1 ring-border">
                      {relationshipStatus}
                    </span>
                  ) : null}
                  <WebSearchBadge />
                </div>
                {isEnded ? (
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span>这段对话已经收束</span>
                  </div>
                ) : null}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link
                className={buttonVariants({ variant: "outline", size: "sm", className: "hidden rounded-full border-border bg-card/85 text-foreground shadow-sm hover:bg-muted md:inline-flex" })}
                href={`/personas/${detail.persona_id}`}
              >
                <FileText className="size-4" aria-hidden />
                资料
              </Link>
              {!isEnded ? (
                <button
                  type="button"
                  title="移入回收站"
                  onClick={() => setDeleteConfirmOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/85 px-2.5 py-1.5 text-sm text-muted-foreground shadow-sm transition-colors hover:border-destructive/30 hover:bg-destructive/8 hover:text-destructive"
                >
                  <Trash2 className="size-3.5" aria-hidden />
                  <span className="hidden sm:inline text-xs font-medium">删除</span>
                </button>
              ) : null}
            </div>
          </header>

          {error ? (
            <div className="mx-4 mt-3 rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <main className="relative flex min-h-0 flex-1 flex-col">
            {typingHintVisible ? (
              <div className="pointer-events-none absolute top-3 left-1/2 z-10 -translate-x-1/2" aria-live="polite">
                <div className="rounded-full border border-border/60 bg-card/92 px-4 py-2 text-sm text-muted-foreground shadow-sm backdrop-blur">
                  对方正在输入中…
                </div>
              </div>
            ) : null}
            {endingNoticeVisible ? (
              <div className={endingPending ? "pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-foreground/10 px-4 backdrop-blur-[1px]" : "pointer-events-none absolute inset-x-4 top-16 z-10 flex justify-center md:top-20"} aria-live="polite">
                <div className="max-w-sm rounded-3xl border border-primary/20 bg-card/95 px-5 py-4 text-center shadow-lg shadow-primary/10 backdrop-blur">
                  <p className="text-sm font-semibold text-foreground">角色已经回应</p>
                  <p className="mt-1 text-xs leading-6 text-muted-foreground">结局正在结算，请稍候。</p>
                </div>
              </div>
            ) : null}
            <FloatingScrollButton
              visible={showBackToLatest || assistantUnreadBump}
              label={assistantUnreadBump ? "有一条未读的角色回复，点击查看" : "回到最新内容"}
              className="absolute right-4 bottom-24"
              onClick={() => {
                scrollViewportToBottom();
                setAssistantUnreadBump(false);
                setShowBackToLatest(false);
              }}
            >
              <ArrowDown className="size-4" aria-hidden />
              {assistantUnreadBump ? "新回复" : "最新"}
            </FloatingScrollButton>
            <ScrollArea className="min-h-0 flex-1">
              <div className="flex flex-col gap-4 px-4 py-5 md:px-8 md:py-7">
                {messages.length === 0 ? (
                  <div className="mx-auto mt-10 max-w-64 rounded-3xl border border-dashed border-border bg-card/60 px-5 py-4 text-center text-sm text-muted-foreground shadow-sm">
                    发一句话，开始这段对话。
                  </div>
                ) : null}
                {messages.map((m) => {
                  const isUser = m.role === "user";
                  const content = m.display_text ?? m.content;
                  const hasText = content.trim().length > 0;
                  const hasAttachments = m.role === "user" && m.attachment_ids && m.attachment_ids.length > 0;
                  return (
                    <div key={m.id} className={isUser ? "flex justify-end" : "flex justify-start gap-2.5"}>
                      {!isUser ? (
                        <div
                          className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-xl text-xs font-semibold text-white shadow-sm ring-1 ring-white/30"
                          style={{ background: "var(--brand-gradient)" }}
                        >
                          {detail.display_name.slice(0, 1) || "心"}
                        </div>
                      ) : null}
                      <div className={isUser ? "flex max-w-[78%] flex-col items-end gap-2" : "flex max-w-[78%] flex-col items-start gap-2"}>
                        {hasText ? (
                          <div
                            className={
                              isUser
                                ? "rounded-[1.35rem] rounded-tr-md border border-primary/20 bg-primary/12 px-4 py-2.5 text-sm leading-relaxed text-foreground shadow-sm"
                                : "rounded-[1.35rem] rounded-tl-md border border-border/60 bg-card px-4 py-2.5 text-sm leading-relaxed text-foreground shadow-sm"
                            }
                          >
                            <div className="whitespace-pre-wrap">{content}</div>
                          </div>
                        ) : null}
                        {hasAttachments ? (
                          <MessageAttachmentCapsules
                            attachmentIds={m.attachment_ids ?? []}
                            previewById={attachmentPreviewById}
                            onImageLoad={scrollViewportToBottom}
                          />
                        ) : null}
                      </div>
                    </div>
                  );
                })}
                <div ref={bottomRef} />
              </div>
            </ScrollArea>

            <div className={cn(
              "shrink-0 border-t border-border/60 bg-card/90 px-4 py-3 backdrop-blur-xl md:px-6",
              isEmbedded
                ? "pb-[calc(env(safe-area-inset-bottom)+0.75rem)] md:pb-3"
                : "pb-[calc(env(safe-area-inset-bottom)+5.5rem)] lg:pb-3",
            )}>
              {isEnded ? (
                <div className="rounded-3xl border border-border bg-muted/30 p-4 text-center shadow-inner">
                  <p className="text-sm font-medium text-muted-foreground">此段对话已落幕</p>
                  {endingData ? (
                    <div className="mt-3 space-y-3 text-left">
                      <div className={cn("space-y-2 rounded-2xl border p-3 shadow-sm ring-1", endingDisplay.panelClassName)}>
                        <div className="flex items-center gap-2">
                          <span className={cn("inline-flex size-7 items-center justify-center rounded-2xl ring-1", endingDisplay.iconClassName)}>
                            <HeartHandshake className="size-3.5" aria-hidden />
                          </span>
                          <p className={cn("text-xs font-semibold", endingDisplay.titleClassName)}>
                            {endingDisplay.label}
                          </p>
                        </div>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{endingData.evaluation}</p>
                      </div>
                      {endingData.user_review ? (
                        <div className="space-y-1 rounded-2xl border border-border bg-card/70 p-3">
                          <p className="text-xs font-semibold text-muted-foreground">复盘</p>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{endingData.user_review}</p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <AttachmentUploader
                    scene="character_chat"
                    conversationId={characterId}
                    draftTurnId={draftTurnId}
                    attachmentIds={attachmentIds}
                    onAttachmentIdsChange={setAttachmentIds}
                    disabled={textareaDisabled || sending}
                  />
                  <div className="flex items-end gap-2 rounded-[1.5rem] border border-border bg-muted/50 p-2 shadow-inner">
                    <Textarea
                      className="max-h-32 min-h-11 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-[15px] leading-relaxed text-foreground shadow-none focus-visible:ring-0"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder="输入消息…"
                      rows={1}
                      disabled={textareaDisabled}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          if (sendDisabled) return;
                          e.preventDefault();
                          void sendMessage();
                        }
                      }}
                    />
                    <Button
                      type="button"
                      size="icon-lg"
                      variant="outline"
                      className={`size-11 shrink-0 rounded-full border-0 shadow-sm transition-all ${sendDisabled ? "bg-muted text-muted-foreground" : "text-white hover:brightness-110 shadow-primary/20"}`}
                      style={sendDisabled ? undefined : { background: "var(--brand-gradient)" }}
                      aria-label="发送"
                      disabled={sendDisabled}
                      onClick={() => void sendMessage()}
                    >
                      <Send className="size-4" strokeWidth={2.25} aria-hidden />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>

    <ConfirmDialog
      title="移入角色回收站？"
      description={`将「${detail?.display_name || "该角色"}」移入会话回收站，之后可在 30 天内恢复。`}
      confirmLabel="移入回收站"
      confirmVariant="destructive"
      open={deleteConfirmOpen}
      onOpenChange={(open) => { if (!open && !deleteLoading) setDeleteConfirmOpen(false); }}
      onConfirm={() => void deleteCharacter()}
      loading={deleteLoading}
    />
    </>
  );
}
