import { cn } from "@/lib/utils";

interface HairlineRuleProps {
  ornament?: string;
  className?: string;
}

export function HairlineRule({ ornament, className }: HairlineRuleProps) {
  if (!ornament) {
    return (
      <hr
        className={cn("border-0 border-t border-[var(--hairline)]", className)}
        aria-hidden
      />
    );
  }
  return (
    <div className={cn("flex items-center gap-3", className)} aria-hidden>
      <span className="h-px flex-1 bg-[var(--hairline)]" />
      <span className="text-[11px] text-muted-foreground/60">{ornament}</span>
      <span className="h-px flex-1 bg-[var(--hairline)]" />
    </div>
  );
}
