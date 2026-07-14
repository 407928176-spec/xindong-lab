import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatusBadgeTone = "unread" | "ended" | "online" | "pinned" | "archive" | "neutral" | "danger";

interface StatusBadgeProps {
  children: ReactNode;
  tone?: StatusBadgeTone;
  className?: string;
}

const toneClass: Record<StatusBadgeTone, string> = {
  unread: "bg-primary/10 text-primary ring-primary/20",
  ended: "bg-amber-50 text-amber-700 ring-amber-100",
  online: "bg-muted text-muted-foreground ring-border",
  pinned: "bg-muted text-muted-foreground ring-border",
  archive: "bg-muted text-muted-foreground ring-border",
  neutral: "bg-muted text-muted-foreground ring-border",
  danger: "bg-destructive/10 text-destructive ring-destructive/20",
};

export function StatusBadge({ children, tone = "neutral", className }: StatusBadgeProps) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1", toneClass[tone], className)}>
      {children}
    </span>
  );
}
