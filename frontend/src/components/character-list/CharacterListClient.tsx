"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Archive, ArrowUp, Library, MessageCircle, Pin, PinOff } from "lucide-react";

import { CharacterChatClient } from "@/components/character-chat/CharacterChatClient";
import { EmptyPersonaGuideDialog } from "@/components/onboarding/EmptyPersonaGuideDialog";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui-patterns/EmptyState";
import { FloatingScrollButton } from "@/components/ui-patterns/FloatingScrollButton";
import { StatusBadge } from "@/components/ui-patterns/StatusBadge";
import { ConversationListItem } from "@/components/ui-patterns/ConversationListItem";
import { apiFetch, apiJson } from "@/lib/api-client";
import { clearPendingPreview, getPendingPreview, getPendingPreviewRecord } from "@/lib/character-chat-pending";
import { DRAFT_CHANGED_EVENT, getDraft } from "@/lib/character-chat-draft";
import type { CharacterListItem } from "@/types/character";
import type { PersonaListItem } from "@/types/persona";

interface CharacterListClientProps {
  initialSelectedCharacterId?: string;
}

export function CharacterListClient({ initialSelectedCharacterId }: CharacterListClientProps = {}) {
  const [items, setItems] = useState<CharacterListItem[]>([]);
  const [showPersonaGuide, setShowPersonaGuide] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [unreadIds, setUnreadIds] = useState<Set<string>>(new Set());
  const [pinningId, setPinningId] = useState<string | null>(null);
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(initialSelectedCharacterId ?? null);
  const [isDesktop, setIsDesktop] = useState(false);
  const listScrollRef = useRef<HTMLDivElement | null>(null);
  const scrollIdleTimerRef = useRef<number | null>(null);
  const [showListBackTop, setShowListBackTop] = useState(false);
  const [listScrollbarActive, setListScrollbarActive] = useState(false);
  // 草稿变化时强制重新渲染列表，preview 取值会重新读取 localStorage
  const [draftRefreshKey, setDraftRefreshKey] = useState(0);

  useEffect(() => {
    const refresh = (): void => setDraftRefreshKey((k) => k + 1);
    window.addEventListener(DRAFT_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(DRAFT_CHANGED_EVENT, refresh);
  }, []);

  const fetchCharacters = useCallback(async (signal?: AbortSignal): Promise<CharacterListItem[] | null> => {
    const res = await apiFetch("/api/characters", { method: "GET", signal });
    if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`);
    const data = (await res.json()) as CharacterListItem[];
    for (const item of data) {
      const pendingPreview = getPendingPreviewRecord(item.id);
      if (!pendingPreview) continue;
      const serverPreview = item.last_message_preview?.trim();
      const serverUpdatedAt = Number.isNaN(Date.parse(item.updated_at)) ? 0 : Date.parse(item.updated_at);
      if (serverPreview === pendingPreview.content.trim() || (pendingPreview.createdAt > 0 && serverUpdatedAt >= pendingPreview.createdAt)) {
        clearPendingPreview(item.id);
      }
    }
    return data;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchCharacters(controller.signal)
      .then((data) => { if (data) setItems(data); })
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== "AbortError") {
          setError(e.message);
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [fetchCharacters]);

  useEffect(() => {
    let cancelled = false;
    const refresh = (): void => {
      fetchCharacters()
        .then((data) => {
          if (!cancelled && data) setItems(data);
        })
        .catch((e: unknown) => {
          if (!cancelled) setError(e instanceof Error ? e.message : "未知错误");
        });
    };
    window.addEventListener("xd:characters-changed", refresh);
    return () => {
      cancelled = true;
      window.removeEventListener("xd:characters-changed", refresh);
    };
  }, [fetchCharacters]);

  // 读取 localStorage 中的未读标记
  const scanUnread = useCallback((): void => {
    const s = new Set<string>();
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k?.startsWith("xd.unreadReply.")) {
        s.add(k.slice("xd.unreadReply.".length));
      }
    }
    setUnreadIds(s);
  }, []);

  // 列表加载完成后扫描一次
  useEffect(() => {
    scanUnread();
  }, [items, scanUnread]);

  // 实时响应同标签页内的未读变化（由聊天页 dispatch xd:unread-changed 触发）
  useEffect(() => {
    window.addEventListener("xd:unread-changed", scanUnread);
    return () => window.removeEventListener("xd:unread-changed", scanUnread);
  }, [scanUnread]);

  async function togglePin(c: CharacterListItem): Promise<void> {
    setPinningId(c.id);
    try {
      const res = await apiFetch(`/api/characters/${c.id}/pin`, { method: "POST" });
      if (!res.ok) throw new Error(`置顶操作失败（HTTP ${res.status}）`);
      // 重新拉取列表以获得服务端排序后的顺序
      const refreshed = await fetchCharacters();
      if (refreshed) setItems(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setPinningId(null);
    }
  }

  // 登录后检测人设库是否为空，若是则强引导创建人设
  useEffect(() => {
    apiJson<PersonaListItem[]>("/api/personas")
      .then((list) => { if (list.length === 0) setShowPersonaGuide(true); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const sync = (): void => setIsDesktop(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    return () => {
      if (scrollIdleTimerRef.current !== null) {
        window.clearTimeout(scrollIdleTimerRef.current);
      }
    };
  }, []);

  const activeItems = items;

  useEffect(() => {
    if (!isDesktop) return;
    if (activeItems.length === 0) {
      setSelectedCharacterId(null);
      return;
    }
    setSelectedCharacterId((prev) => {
      if (prev && activeItems.some((item) => item.id === prev)) return prev;
      if (initialSelectedCharacterId && activeItems.some((item) => item.id === initialSelectedCharacterId)) {
        return initialSelectedCharacterId;
      }
      return activeItems[0]?.id ?? null;
    });
  }, [activeItems, initialSelectedCharacterId, isDesktop]);

  const hasDraftFor = (c: CharacterListItem) => c.status !== "ending_unread" && getDraft(c.id).trim().length > 0;
  const pinnedItems = activeItems.filter((c) => c.is_pinned);
  const regularItems = activeItems.filter((c) => !c.is_pinned);
  const draftRegularItems = regularItems.filter((c) => hasDraftFor(c));
  const otherRegularItems = regularItems.filter((c) => !hasDraftFor(c));
  const selectedCharacter = useMemo(
    () => activeItems.find((item) => item.id === selectedCharacterId) ?? null,
    [activeItems, selectedCharacterId],
  );

  function renderConversation(c: CharacterListItem) {
    void draftRefreshKey; // 仅用于触发依赖
    const pendingPreview = getPendingPreview(c.id);
    // 已落幕角色不显示草稿（终局确认后草稿应已清除，此处作防御）
    const draftText = pendingPreview || c.status === "ending_unread" ? "" : getDraft(c.id);
    const hasDraft = draftText.trim().length > 0;
    const preview = pendingPreview
      ?? (hasDraft ? `[草稿]：${draftText}` : c.last_message_preview);
    const previewVariant: "normal" | "draft" = hasDraft ? "draft" : "normal";
    const badges = (
      <>
        {c.status === "ending_unread" ? <StatusBadge tone="ended">已落幕</StatusBadge> : null}
        {unreadIds.has(c.id) && c.status !== "ending_unread" ? <StatusBadge tone="unread">新消息</StatusBadge> : null}
        {c.is_pinned ? <StatusBadge tone="pinned">置顶</StatusBadge> : null}
      </>
    );

    return (
      <ConversationListItem
        key={c.id}
        href={`/characters/${c.id}`}
        name={c.display_name || "未命名角色"}
        preview={preview ? (hasDraft ? preview : `最近：${preview}`) : "暂无消息"}
        previewVariant={previewVariant}
        meta={`更新：${new Date(c.updated_at).toLocaleString()}`}
        badges={badges}
        pinned={c.is_pinned}
        active={isDesktop && selectedCharacterId === c.id}
        onClick={(e) => {
          if (!isDesktop) return;
          e.preventDefault();
          setSelectedCharacterId(c.id);
        }}
        actions={
          <button
            type="button"
            title={c.is_pinned ? "取消置顶" : "置顶"}
            disabled={pinningId === c.id}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              void togglePin(c);
            }}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40"
          >
            {c.is_pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
            {c.is_pinned ? "取消置顶" : "置顶"}
          </button>
        }
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 lg:flex-row lg:gap-0 lg:overflow-hidden lg:rounded-[1.75rem] lg:border lg:border-border lg:bg-card lg:shadow-sm">
      <section className="flex min-h-0 flex-col overflow-hidden rounded-[1.5rem] border border-border bg-card lg:h-full lg:w-[22rem] lg:shrink-0 lg:rounded-none lg:border-0 lg:border-r">
        <div className="border-b border-[var(--hairline)] px-4 py-5">
          <div className="flex items-center">
            <h1 className="font-heading text-[26px] font-semibold tracking-tight text-foreground">心动实验室</h1>
          </div>
        </div>

        <div className="relative min-h-0 flex-1">
          <FloatingScrollButton
            visible={showListBackTop}
            label="回到顶部"
            className="absolute right-3 bottom-5"
            onClick={() => listScrollRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
          >
            <ArrowUp className="size-4" aria-hidden />
            顶部
          </FloatingScrollButton>
          <div
            ref={listScrollRef}
            className={`homepage-character-scroll min-h-0 h-full space-y-4 overflow-y-auto p-3 pb-28 lg:pb-3 ${listScrollbarActive ? "is-scrolling" : ""}`}
            onMouseEnter={() => setListScrollbarActive(true)}
            onMouseLeave={() => setListScrollbarActive(false)}
            onScroll={(e) => {
              setShowListBackTop(e.currentTarget.scrollTop > 240);
              setListScrollbarActive(true);
              if (scrollIdleTimerRef.current !== null) window.clearTimeout(scrollIdleTimerRef.current);
              scrollIdleTimerRef.current = window.setTimeout(() => setListScrollbarActive(false), 900);
            }}
          >
          {error ? (
            <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          {loading ? <p className="px-2 py-4 text-sm text-muted-foreground">加载中…</p> : null}

          {!loading && activeItems.length === 0 ? (
            <EmptyState
              title="还没有进行中的角色会话"
              description="你可以去人设库开始新的聊天，或到缘散录查看已终局的角色。"
              actions={
                <>
                  <Link className={buttonVariants({ variant: "hero", className: "rounded-full" })} href="/personas">
                    <Library className="size-4" aria-hidden />
                    去人设库
                  </Link>
                  <Link className={buttonVariants({ variant: "outline", className: "rounded-full" })} href="/archive">
                    <Archive className="size-4" aria-hidden />
                    缘散录
                  </Link>
                </>
              }
            />
          ) : null}

          {pinnedItems.length > 0 ? (
            <div className="space-y-2">
              <p className="flex items-center gap-2 px-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                <span className="font-heading text-[12px] italic normal-case tracking-normal">i.</span>
                置顶
              </p>
              <div className="space-y-2">{pinnedItems.map(renderConversation)}</div>
            </div>
          ) : null}

          {(draftRegularItems.length > 0 || otherRegularItems.length > 0) ? (
            <div className="space-y-2">
              {pinnedItems.length > 0 ? (
                <p className="flex items-center gap-2 px-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  <span className="font-heading text-[12px] italic normal-case tracking-normal">ii.</span>
                  全部会话
                </p>
              ) : null}
              <div className="space-y-2">{[...draftRegularItems, ...otherRegularItems].map(renderConversation)}</div>
            </div>
          ) : null}
          </div>
        </div>

      </section>

      <aside className="hidden min-h-0 flex-col overflow-hidden bg-muted/60 lg:flex lg:h-full lg:flex-1 lg:min-w-0">
        {isDesktop ? (
          selectedCharacter ? (
            <CharacterChatClient characterId={selectedCharacter.id} variant="embedded" />
          ) : (
            <div className="flex h-full min-h-0 flex-col">
              <div className="border-b border-border bg-card px-6 py-5">
                <h2 className="text-lg font-semibold text-foreground">会话内容</h2>
                <p className="mt-1 text-sm text-muted-foreground">从左侧选择一个角色，右侧会直接切换到对应聊天。</p>
              </div>
              <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
                <div className="flex size-14 items-center justify-center rounded-3xl bg-card text-muted-foreground shadow-sm ring-1 ring-border">
                  <MessageCircle className="size-6" aria-hidden />
                </div>
                <h3 className="mt-5 text-2xl font-semibold tracking-tight text-foreground">选择一个会话开始聊天</h3>
                <p className="mt-3 max-w-md text-sm leading-7 text-muted-foreground">
                  左侧保留你当前所有进行中的关系，选中后会在右侧原地继续，不再跳出新的聊天页。
                </p>
              </div>
            </div>
          )
        ) : null}
      </aside>

      <EmptyPersonaGuideDialog
        open={showPersonaGuide}
        onConfirm={() => { window.location.href = "/personas/new"; }}
      />
    </div>
  );
}
