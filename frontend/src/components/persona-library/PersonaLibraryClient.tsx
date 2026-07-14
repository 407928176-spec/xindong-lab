"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageCircle, Plus, Pin, PinOff, Trash2 } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageShell } from "@/components/shell/PageShell";
import { SectionHeader } from "@/components/shell/SectionHeader";
import { EmptyState } from "@/components/ui-patterns/EmptyState";
import { ChatAvatar } from "@/components/ui-patterns/ChatAvatar";
import { StatusBadge } from "@/components/ui-patterns/StatusBadge";
import { apiFetch } from "@/lib/api-client";
import { getPendingPrewarm } from "@/lib/character-prewarm";
import type { PersonaDeletePreviewResponse, PersonaListItem } from "@/types/persona";
import type { CharacterCreatedResponse } from "@/types/character";

export function PersonaLibraryClient() {
  const router = useRouter();
  const [items, setItems] = useState<PersonaListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingId, setStartingId] = useState<string | null>(null);
  const [initializingId, setInitializingId] = useState<string | null>(null);
  const [personaPendingDelete, setPersonaPendingDelete] = useState<PersonaListItem | null>(null);
  const [deletePreview, setDeletePreview] = useState<PersonaDeletePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [pinningId, setPinningId] = useState<string | null>(null);

  const fetchPersonas = useCallback(async (): Promise<PersonaListItem[]> => {
    const res = await apiFetch("/api/personas", { method: "GET" });
    if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`);
    return (await res.json()) as PersonaListItem[];
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPersonas()
      .then((data) => { if (!cancelled) setItems(data); })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "未知错误");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchPersonas]);

  async function startChat(personaId: string): Promise<void> {
    setError(null);
    setStartingId(personaId);
    try {
      let characterId: string | null = null;

      const prewarm = getPendingPrewarm(personaId);
      if (prewarm) {
        setInitializingId(personaId); // 预热进行中，显示"初始化中…"
        characterId = await prewarm.catch(() => null);
      }

      if (!characterId) {
        // 无预热或预热失败，走普通 POST（后端会复用已有角色或新建）
        const res = await apiFetch("/api/characters", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ persona_id: personaId }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
          const msg =
            typeof body?.detail === "string" ? body.detail : `创建角色失败（HTTP ${res.status}）`;
          throw new Error(msg);
        }
        characterId = ((await res.json()) as CharacterCreatedResponse).id;
      }

      router.push(`/characters/${characterId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setStartingId(null);
      setInitializingId(null);
    }
  }

  async function confirmDeletePersona(): Promise<void> {
    const p = personaPendingDelete;
    if (!p) return;
    setError(null);
    setDeleteLoading(true);
    try {
      const res = await apiFetch(`/api/personas/${p.id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg =
          typeof body?.detail === "string" ? body.detail : `删除失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }
      setPersonaPendingDelete(null);
      setDeletePreview(null);
      setItems((prev) => prev.filter((x) => x.id !== p.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleDeleteClick(p: PersonaListItem): Promise<void> {
    setError(null);
    setPreviewLoading(true);
    try {
      const res = await apiFetch(`/api/personas/${p.id}/delete-preview`);
      if (!res.ok) throw new Error(`获取删除预览失败（HTTP ${res.status}）`);
      const preview = (await res.json()) as PersonaDeletePreviewResponse;
      setDeletePreview(preview);
      setPersonaPendingDelete(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function togglePin(p: PersonaListItem): Promise<void> {
    setPinningId(p.id);
    try {
      const res = await apiFetch(`/api/personas/${p.id}/pin`, { method: "POST" });
      if (!res.ok) throw new Error(`置顶操作失败（HTTP ${res.status}）`);
      const refreshed = await fetchPersonas();
      setItems(refreshed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setPinningId(null);
    }
  }

  const pinnedItems = items.filter((p) => p.is_pinned);
  const regularItems = items.filter((p) => !p.is_pinned);

  function renderCard(p: PersonaListItem) {
    return (
      <div key={p.id} className="overflow-hidden rounded-[1.25rem] border border-border bg-card shadow-sm">
        <Link href={`/personas/${p.id}`} className="flex gap-3 p-4 transition-colors hover:bg-muted/40">
          <ChatAvatar name={p.display_name || "未命名"} tone="assistant" size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="truncate text-base font-semibold text-foreground">{p.display_name || "未命名"}</h2>
                <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">{p.identity_summary || "暂无描述"}</p>
              </div>
              {p.is_pinned ? <StatusBadge tone="pinned">置顶</StatusBadge> : null}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">创建：{new Date(p.created_at).toLocaleString()}</p>
          </div>
        </Link>
        <div className="flex flex-wrap justify-end gap-2 border-t border-border/60 px-4 py-3">
          <button
            type="button"
            title={p.is_pinned ? "取消置顶" : "置顶"}
            disabled={pinningId === p.id}
            onClick={(e) => { e.preventDefault(); void togglePin(p); }}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40"
          >
            {p.is_pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
            {p.is_pinned ? "取消置顶" : "置顶"}
          </button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="rounded-full"
            disabled={startingId === p.id || deleteLoading || previewLoading}
            onClick={(e) => {
              e.preventDefault();
              void handleDeleteClick(p);
            }}
          >
            <Trash2 className="size-4" aria-hidden />
            移入回收站
          </Button>
          <Button
            type="button"
            size="sm"
            variant="hero"
            className="rounded-full"
            disabled={startingId === p.id}
            onClick={(e) => {
              e.preventDefault();
              void startChat(p.id);
            }}
          >
            <MessageCircle className="size-4" aria-hidden />
            {startingId === p.id
              ? initializingId === p.id
                ? "初始化中…"
                : "创建中…"
              : "开始聊天"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <PageShell size="xl">
      <ConfirmDialog
        open={personaPendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !deleteLoading) {
            setPersonaPendingDelete(null);
            setDeletePreview(null);
          }
        }}
        title="确认删除人设？"
        description={
          personaPendingDelete && deletePreview
            ? (() => {
                const { active_in_progress, ended_characters, archived_characters } = deletePreview;
                if (active_in_progress.length > 0) {
                  return (
                    <span className="text-destructive">
                      该人设下还有 <b>{active_in_progress.length}</b> 个进行中的聊天（
                      {active_in_progress.map((c) => c.display_name).join("、")}
                      ），请先在首页将它们删除后再删除人设。
                    </span>
                  );
                }
                const hasSideEffects = ended_characters.length > 0 || archived_characters.length > 0;
                if (!hasSideEffects) {
                  return `将「${personaPendingDelete.display_name || "未命名"}」移入人设回收站，之后可在 30 天内恢复。`;
                }
                return (
                  <span>
                    将「<b>{personaPendingDelete.display_name || "未命名"}</b>」移入人设回收站。
                    {ended_characters.length > 0 && (
                      <span className="mt-1 block text-muted-foreground">
                        缘散录中还有 {ended_characters.length} 个已结局角色，将一并清除。
                      </span>
                    )}
                    {archived_characters.length > 0 && (
                      <span className="mt-1 block text-muted-foreground">
                        回收站中还有 {archived_characters.length} 个角色，将一并清除。
                      </span>
                    )}
                  </span>
                );
              })()
            : ""
        }
        confirmLabel="移入回收站"
        cancelLabel="取消"
        confirmVariant="destructive"
        loading={deleteLoading}
        confirmDisabled={deletePreview !== null && deletePreview.active_in_progress.length > 0}
        onConfirm={confirmDeletePersona}
      />

      <SectionHeader
        title="人设库"
        description="管理可开启对话的角色档案。选择一个人设，开始一段新的关系模拟。"
        backHref="/"
        backLabel="返回首页"
        backClassName="lg:hidden"
        sticky
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link className={buttonVariants({ variant: "hero", className: "rounded-full px-5" })} href="/personas/new">
              <Plus className="size-4" aria-hidden />
              创建人设
            </Link>
            <Link className={buttonVariants({ variant: "outline", size: "sm", className: "rounded-full" })} href="/personas/archive">
              <Trash2 className="size-4" aria-hidden />
              人设回收站
            </Link>
          </div>
        }
      />

      {error ? (
        <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-muted-foreground text-sm">加载中…</p> : null}

      {!loading && items.length === 0 ? (
        <EmptyState
          title="还没有人设"
          description="先去创建页用对话生成一个吧。"
          actions={
            <Link className={buttonVariants({ variant: "hero", className: "rounded-full" })} href="/personas/new">
              <Plus className="size-4" aria-hidden />
              去创建
            </Link>
          }
        />
      ) : null}

      {/* 置顶区 */}
      {pinnedItems.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
            <Pin size={12} />
            置顶
          </p>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {pinnedItems.map(renderCard)}
          </div>
        </div>
      )}

      {/* 置顶与普通区之间的分割线 */}
      {pinnedItems.length > 0 && regularItems.length > 0 ? (
        <div className="py-1">
          <div className="h-px bg-border" />
        </div>
      ) : null}

      {/* 普通区 */}
      {regularItems.length > 0 && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {regularItems.map(renderCard)}
        </div>
      )}
    </PageShell>
  );
}
