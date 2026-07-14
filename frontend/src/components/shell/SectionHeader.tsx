import type { ReactNode } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

import { cn } from "@/lib/utils";

interface SectionHeaderProps {
  title: string;
  description?: string;
  backHref?: string;
  backLabel?: string;
  backClassName?: string;
  actions?: ReactNode;
  eyebrow?: string;
  className?: string;
  sticky?: boolean;
}

export function SectionHeader({
  title,
  description,
  backHref,
  backLabel = "返回",
  backClassName,
  actions,
  eyebrow,
  className,
  sticky = false,
}: SectionHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-4 rounded-[1.5rem] border border-border/60 bg-card p-4 shadow-sm md:flex-row md:items-end md:justify-between md:p-5",
        sticky && "sticky top-0 z-20 shadow-md shadow-foreground/5",
        className,
      )}
    >
      <div className="min-w-0 space-y-3">
        {backHref ? (
          <Link
            href={backHref}
            className={cn(
              "inline-flex w-fit items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted",
              backClassName,
            )}
          >
            <ChevronLeft className="size-4" aria-hidden />
            {backLabel}
          </Link>
        ) : null}
        <div className="space-y-1">
          {eyebrow ? <p className="font-heading text-[11px] font-medium italic uppercase tracking-[0.22em] text-muted-foreground">{eyebrow}</p> : null}
          <h1 className="truncate font-heading text-2xl font-semibold tracking-tight text-foreground md:text-3xl">{title}</h1>
          {description ? <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2 md:justify-end">{actions}</div> : null}
    </header>
  );
}
