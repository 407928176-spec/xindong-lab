import type { MouseEventHandler, ReactNode } from "react";
import Link from "next/link";

import { ChatAvatar } from "@/components/ui-patterns/ChatAvatar";
import { cn } from "@/lib/utils";

interface ConversationListItemProps {
  href: string;
  name: string;
  preview?: string | null;
  previewVariant?: "normal" | "draft";
  meta?: string;
  badges?: ReactNode;
  actions?: ReactNode;
  pinned?: boolean;
  active?: boolean;
  onClick?: MouseEventHandler<HTMLAnchorElement>;
  className?: string;
}

export function ConversationListItem({
  href,
  name,
  preview,
  previewVariant = "normal",
  meta,
  badges,
  actions,
  pinned = false,
  active = false,
  onClick,
  className,
}: ConversationListItemProps) {
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-[1.1rem] border bg-card transition-all hover:bg-muted/40",
        active
          ? "border-primary/30 bg-primary/5 shadow-[0_1px_3px_oklch(0.20_0.025_200/0.04),0_4px_12px_oklch(0.20_0.025_200/0.06)]"
          : pinned
            ? "border-primary/25 shadow-[0_1px_3px_oklch(0.20_0.025_200/0.03),0_4px_12px_oklch(0.20_0.025_200/0.05)] hover:shadow-[0_1px_4px_oklch(0.20_0.025_200/0.04),0_6px_16px_oklch(0.20_0.025_200/0.07)]"
            : "border-foreground/[0.08] shadow-[0_1px_3px_oklch(0.20_0.025_200/0.03),0_4px_10px_oklch(0.20_0.025_200/0.04)] hover:shadow-[0_1px_4px_oklch(0.20_0.025_200/0.04),0_6px_14px_oklch(0.20_0.025_200/0.06)]",
        className,
      )}
    >
      {/* 顶部渐变装饰条 — 仅置顶 / 激活时显示，普通卡片克制留白 */}
      {(active || pinned) && (
        <div
          className={cn(
            "absolute inset-x-0 top-0 h-[2.5px] rounded-t-[1.1rem]",
            active ? "opacity-100" : "opacity-70",
          )}
          style={{ background: "var(--brand-gradient)" }}
          aria-hidden
        />
      )}
      {/* 选中态左侧渐变竖线 */}
      {active && (
        <div
          className="absolute inset-y-0 left-0 w-[3px] rounded-r-full"
          style={{ background: "var(--brand-gradient)" }}
          aria-hidden
        />
      )}
      <Link href={href} onClick={onClick} className="flex min-w-0 gap-3 px-3 py-3.5 pr-4">
        <ChatAvatar name={name} className="shadow-none" />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-heading text-[15px] font-semibold tracking-tight text-foreground">{name || "未命名"}</p>
              {meta ? <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{meta}</p> : null}
            </div>
            {(badges || active) ? (
              <div className="flex shrink-0 flex-wrap justify-end gap-1">
                {badges}
                {active && <span className="text-[10px] italic text-primary/70">正在聊天</span>}
              </div>
            ) : null}
          </div>
          <p
            className={cn(
              "mt-1.5 line-clamp-2 text-sm leading-relaxed",
              previewVariant === "draft" ? "text-accent" : "text-muted-foreground",
            )}
          >
            {preview || "暂无消息"}
          </p>
        </div>
      </Link>
      {actions ? (
        <div className="flex items-center justify-end gap-2 border-t border-border/60 px-3 py-2">
          {actions}
        </div>
      ) : null}
    </div>
  );
}
