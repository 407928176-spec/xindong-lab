"use client";

import { useCallback, useEffect, useState } from "react";
import { RotateCcw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageShell } from "@/components/shell/PageShell";
import { SectionHeader } from "@/components/shell/SectionHeader";
import { EmptyState } from "@/components/ui-patterns/EmptyState";
import { apiFetch } from "@/lib/api-client";
import type { CharacterListItem } from "@/types/character";

export function CharacterArchiveClient() {
  const [items, setItems] = useState<CharacterListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [characterPendingDelete, setCharacterPendingDelete] = useState<CharacterListItem | null>(null);
  const [clearOpen, setClearOpen] = useState(false);
  const [clearLoading, setClearLoading] = useState(false);

  const fetchArchived = useCallback(async (): Promise<CharacterListItem[]> => {
    const res = await apiFetch("/api/characters/archive", { method: "GET" });
    if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`);
    return (await res.json()) as CharacterListItem[];
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchArchived()
      .then((data) => { if (!cancelled) setItems(data); })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "未知错误");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchArchived]);

  async function restoreCharacter(characterId: string): Promise<void> {
    setError(null);
    setRestoreLoading(true);
    try {
      const res = await apiFetch(`/api/characters/${characterId}/restore`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg =
          typeof body?.detail === "string" ? body.detail : `恢复失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }
      setItems((prev) => prev.filter((x) => x.id !== characterId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setRestoreLoading(false);
    }
  }

  async function confirmClearArchive(): Promise<void> {
    setError(null);
    setClearLoading(true);
    try {
      const res = await apiFetch("/api/characters/archive", { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg =
          typeof body?.detail === "string" ? body.detail : `清空失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }
      setItems([]);
      setClearOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setClearLoading(false);
    }
  }

  async function confirmDeleteCharacter(): Promise<void> {
    const c = characterPendingDelete;
    if (!c) return;
    setError(null);
    setDeleteLoading(true);
    try {
      const res = await apiFetch(`/api/characters/${c.id}/permanently`, { method: "DELETE" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
        const msg =
          typeof body?.detail === "string" ? body.detail : `删除失败（HTTP ${res.status}）`;
        throw new Error(msg);
      }
      setCharacterPendingDelete(null);
      setItems((prev) => prev.filter((x) => x.id !== c.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setDeleteLoading(false);
    }
  }

  if (loading) {
    return (
      <PageShell size="lg">
        <p className="text-sm text-muted-foreground">加载中…</p>
      </PageShell>
    );
  }

  return (
    <PageShell size="xl">
      {error && (
        <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <SectionHeader
        title="角色回收站"
        description="已删除的聊天保留 30 天，超期自动删除。"
        backHref="/"
        backLabel="返回首页"
        sticky
        actions={
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="rounded-full border-destructive/30 text-destructive hover:bg-destructive/5"
            disabled={items.length === 0 || clearLoading}
            onClick={() => setClearOpen(true)}
          >
            <Trash2 className="size-4" aria-hidden />
            清空回收站
          </Button>
        }
      />

      {items.length === 0 ? (
        <EmptyState title="回收站为空" description="这里暂时没有被移入回收站的角色会话。" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {items.map((item) => (
            <Card key={item.id} className="rounded-[1.25rem] border-border bg-card shadow-sm">
              <CardHeader>
                <CardTitle>{item.display_name || "未命名角色"}</CardTitle>
                <CardDescription>
                  已删除的会话记录
                </CardDescription>
              </CardHeader>
              <CardContent className="text-sm">
                <p className="text-muted-foreground line-clamp-2 text-xs">
                  {item.last_message_preview ? `最近：${item.last_message_preview}` : "暂无消息"}
                </p>
                <p className="text-muted-foreground text-xs">更新：{new Date(item.updated_at).toLocaleString()}</p>
              </CardContent>
              <CardFooter className="flex flex-wrap gap-2 border-t bg-muted/10 px-6 py-3">
                <Button
                  type="button"
                  size="sm"
                  disabled={restoreLoading}
                  onClick={() => void restoreCharacter(item.id)}
                >
                  <RotateCcw className="size-4" aria-hidden />
                  恢复
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  disabled={deleteLoading}
                  onClick={() => setCharacterPendingDelete(item)}
                >
                  <Trash2 className="size-4" aria-hidden />
                  永久删除
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        title="永久删除角色"
        description={`确认永久删除角色"${characterPendingDelete?.display_name}"？删除后无法恢复。`}
        confirmLabel="永久删除"
        confirmVariant="destructive"
        open={characterPendingDelete !== null}
        onOpenChange={(open) => { if (!open && !deleteLoading) setCharacterPendingDelete(null); }}
        onConfirm={() => void confirmDeleteCharacter()}
        loading={deleteLoading}
      />

      <ConfirmDialog
        title="清空角色回收站？"
        description="将永久删除回收站中的全部角色聊天及其消息记录，操作不可撤销。"
        confirmLabel="清空"
        confirmVariant="destructive"
        open={clearOpen}
        onOpenChange={(open) => { if (!open && !clearLoading) setClearOpen(false); }}
        onConfirm={() => void confirmClearArchive()}
        loading={clearLoading}
      />
    </PageShell>
  );
}
