import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function EmptyState({ title, description, actions }: EmptyStateProps) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center px-8 py-10 text-center">
      <div className="mb-4 h-px w-12 bg-[var(--hairline-strong)]" />
      <h2 className="font-heading text-xl font-semibold tracking-tight text-foreground">{title}</h2>
      {description ? (
        <p className="mt-2 max-w-sm font-heading text-[13px] italic leading-relaxed text-muted-foreground">{description}</p>
      ) : null}
      {actions ? <div className="mt-5 flex flex-wrap justify-center gap-2">{actions}</div> : null}
    </div>
  );
}
