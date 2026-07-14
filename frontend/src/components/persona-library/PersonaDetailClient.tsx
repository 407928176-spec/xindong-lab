"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, MessageCircle } from "lucide-react";

import { VisibleLayerPreview } from "@/components/persona-create/VisibleLayerPreview";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageShell } from "@/components/shell/PageShell";
import { SectionHeader } from "@/components/shell/SectionHeader";
import { ChatAvatar } from "@/components/ui-patterns/ChatAvatar";
import { apiFetch } from "@/lib/api-client";
import type { PersonaDeletePreviewResponse, PersonaDetailResponse } from "@/types/persona";
import type { CharacterCreatedResponse } from "@/types/character";

interface PersonaDetailClientProps {
  personaId: string;
}

export function PersonaDetailClient({ personaId }: PersonaDetailClientProps) {
  const router = useRouter();
  const [detail, setDetail] = useState<PersonaDetailResponse | null>(null);
  const [characterSummary, setCharacterSummary] = useState<PersonaDeletePreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingChat, setStartingChat] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const [detailRes, previewRes] = await Promise.all([
          apiFetch(`/api/personas/${personaId}`, { method: "GET" }),
          apiFetch(`/api/personas/${personaId}/delete-preview`, { method: "GET" }),
        ]);
        if (!detailRes.ok) {
          const body = (await detailRes.json().catch(() => null)) as { detail?: unknown } | null;
          const msg =
            typeof body?.detail === "string" ? body.detail : `加载失败（HTTP ${detailRes.status}）`;
          throw new Error(msg);
        }
        const data = (await detailRes.json()) as PersonaDetailResponse;
        const preview = previewRes.ok
          ? ((await previewRes.json()) as PersonaDeletePreviewResponse)
          : null;
        if (!cancelled) {
          setDetail(data);
          setCharacterSummary(preview);
        }
      } catch (e) {
        if (!cancelled) {
          setDetail(null);
          setError(e instanceof Error ? e.message : "未知错误");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [personaId]);

  async function startChat(): Promise<void> {
    setError(null);
    setStartingChat(true);
    try {
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
      const characterId = ((await res.json()) as CharacterCreatedResponse).id;
      router.push(`/characters/${characterId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "未知错误");
    } finally {
      setStartingChat(false);
    }
  }

  if (loading) {
    return (
      <PageShell size="md">
        <p className="text-sm text-muted-foreground">加载中…</p>
      </PageShell>
    );
  }

  if (error || !detail) {
    return (
      <PageShell size="md">
        <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error ?? "未找到人设"}
        </div>
        <Link className={buttonVariants({ variant: "outline", className: "w-fit rounded-full" })} href="/personas">
          <ChevronLeft className="size-4" aria-hidden />
          返回人设库
        </Link>
      </PageShell>
    );
  }

  return (
    <PageShell size="lg">
        {error && (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
        <SectionHeader
          title={detail.display_name || "未命名"}
          description={`创建：${new Date(detail.created_at).toLocaleString()}`}
          backHref="/personas"
          backLabel="返回人设库"
          sticky
          actions={
            <Button variant="hero" className="rounded-full" disabled={startingChat} onClick={() => void startChat()}>
              <MessageCircle className="size-4" aria-hidden />
              {startingChat ? "创建中…" : "开始聊天"}
            </Button>
          }
        />
        <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <aside className="rounded-[1.75rem] border border-border/60 bg-card/85 p-5 shadow-sm">
            <ChatAvatar name={detail.display_name || "未命名"} tone="assistant" size="lg" />
            <h2 className="mt-4 text-lg font-semibold text-foreground">角色档案</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">这里记录的是用户可见的人设信息，用于开启新的对话关系。</p>

            {characterSummary && (
              <div className="mt-5 border-t border-border/50 pt-4">
                <h3 className="mb-3 text-sm font-medium text-foreground">该人设下的角色</h3>
                {characterSummary.active_in_progress.length === 0 &&
                 characterSummary.ended_characters.length === 0 &&
                 characterSummary.archived_characters.length === 0 ? (
                  <p className="text-xs text-muted-foreground">暂无角色</p>
                ) : (
                  <div className="space-y-3 text-xs">
                    {characterSummary.active_in_progress.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-muted-foreground">进行中</p>
                        <ul className="space-y-1">
                          {characterSummary.active_in_progress.map((c) => (
                            <li key={c.id} className="flex items-center gap-2 text-foreground/80">
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                              <Link href={`/characters/${c.id}`} className="truncate hover:underline">{c.display_name}</Link>
                              <span className="ml-auto shrink-0 text-muted-foreground">{new Date(c.updated_at).toLocaleDateString()}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {characterSummary.ended_characters.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-muted-foreground">缘散录</p>
                        <ul className="space-y-1">
                          {characterSummary.ended_characters.map((c) => (
                            <li key={c.id} className="flex items-center gap-2 text-muted-foreground">
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rose-400" />
                              <span className="truncate">{c.display_name}</span>
                              <span className="ml-auto shrink-0">{new Date(c.updated_at).toLocaleDateString()}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {characterSummary.archived_characters.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-muted-foreground">回收站</p>
                        <ul className="space-y-1">
                          {characterSummary.archived_characters.map((c) => (
                            <li key={c.id} className="flex items-center gap-2 text-muted-foreground/70">
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/40" />
                              <span className="truncate">{c.display_name}</span>
                              <span className="ml-auto shrink-0">{new Date(c.updated_at).toLocaleDateString()}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </aside>
          <Card className="rounded-[1.75rem] border-border/60 bg-card/85 shadow-sm">
            <CardHeader>
              <CardTitle>可见层档案</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <VisibleLayerPreview vl={detail.visible_layer} />
            </CardContent>
          </Card>
        </div>
    </PageShell>
  );
}
