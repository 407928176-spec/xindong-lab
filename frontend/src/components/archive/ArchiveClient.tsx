"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeartHandshake, MessageCircle } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { PageShell } from "@/components/shell/PageShell";
import { SectionHeader } from "@/components/shell/SectionHeader";
import { EmptyState } from "@/components/ui-patterns/EmptyState";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiFetch } from "@/lib/api-client";
import { getEndingDisplay } from "@/lib/ending-display";
import { cn } from "@/lib/utils";
import type { CharacterListItem } from "@/types/character";

export function ArchiveClient() {
  const [items, setItems] = useState<CharacterListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch("/api/characters/ended", { method: "GET" });
        if (!res.ok) throw new Error(`加载失败（HTTP ${res.status}）`);
        const data = (await res.json()) as CharacterListItem[];
        if (!cancelled) setItems(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "未知错误");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageShell size="xl">
      <SectionHeader
        title="缘散录"
        description="已到达终局的对话存档。"
        backHref="/"
        backLabel="返回首页"
        sticky
      />

      {error ? (
        <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-muted-foreground text-sm">加载中…</p> : null}

      {!loading && items.length === 0 ? (
        <EmptyState
          title="暂无终局记录"
          description="还没有任何对话到达终局。"
        />
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {items.map((c) => {
          const endingDisplay = getEndingDisplay(c.ending?.result);
          return (
          <Card key={c.id} className={cn("rounded-[1.25rem] shadow-sm", c.ending ? endingDisplay.cardClassName : "border-border bg-card")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                {c.ending ? (
                  <span className={cn("inline-flex size-8 shrink-0 items-center justify-center rounded-2xl ring-1", endingDisplay.iconClassName)}>
                    <HeartHandshake className="size-4" aria-hidden />
                  </span>
                ) : null}
                <span className="min-w-0 truncate">{c.display_name || "未命名角色"}</span>
                {c.ending ? (
                  <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", endingDisplay.badgeClassName)}>{endingDisplay.label}</span>
                ) : null}
              </CardTitle>
              <CardDescription>
                已封存的对话记录
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              {c.ending?.evaluation ? (
                <p className={cn("rounded-2xl border p-3 text-sm leading-relaxed whitespace-pre-wrap ring-1", endingDisplay.panelClassName)}>{c.ending.evaluation}</p>
              ) : null}
              <p className="text-muted-foreground line-clamp-2 text-xs">
                {c.last_message_preview ? `最近：${c.last_message_preview}` : "暂无消息"}
              </p>
              <p className="text-muted-foreground text-xs">
                更新：{new Date(c.updated_at).toLocaleString()}
              </p>
            </CardContent>
            <CardFooter className="flex flex-wrap gap-2 border-t bg-muted/10 px-6 py-3">
              <Link
                className={buttonVariants({ variant: "outline", size: "sm", className: "rounded-full" })}
                href={`/characters/${c.id}?from=archive`}
              >
                <MessageCircle className="size-4" aria-hidden />
                查看对话
              </Link>
            </CardFooter>
          </Card>
          );
        })}
      </div>
    </PageShell>
  );
}
