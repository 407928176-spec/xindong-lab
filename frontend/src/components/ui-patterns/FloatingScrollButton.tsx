"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface FloatingScrollButtonProps {
  visible: boolean;
  onClick: () => void;
  label: string;
  children: ReactNode;
  className?: string;
}

export function FloatingScrollButton({ visible, onClick, label, children, className }: FloatingScrollButtonProps) {
  if (!visible) return null;

  return (
    <button
      type="button"
      className={cn(
        "z-20 inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium text-white shadow-lg shadow-foreground/10 backdrop-blur transition-all hover:brightness-110",
        className,
      )}
      style={{ background: "var(--brand-gradient)" }}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
