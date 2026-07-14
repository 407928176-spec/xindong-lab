import { Plus } from "lucide-react";

import { cn } from "@/lib/utils";

interface AttachmentPlusButtonProps {
  disabled?: boolean;
  uploading?: boolean;
  count: number;
  max: number;
  onClick: () => void;
  className?: string;
}

export function AttachmentPlusButton({ disabled = false, uploading = false, count, max, onClick, className }: AttachmentPlusButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex size-10 shrink-0 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm transition-colors hover:border-primary/30 hover:bg-primary/8 hover:text-primary disabled:pointer-events-none disabled:opacity-45",
        className,
      )}
      disabled={disabled || uploading || count >= max}
      onClick={onClick}
      aria-label={uploading ? "附件上传中" : `添加附件，已添加 ${count}/${max}`}
      title={uploading ? "上传中…" : `添加附件 (${count}/${max})`}
    >
      <Plus className="size-5" strokeWidth={2.25} aria-hidden />
    </button>
  );
}
