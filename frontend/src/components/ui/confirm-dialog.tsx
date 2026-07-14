"use client";

import { type ReactNode } from "react";
import { Check, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  /** description 下方的额外内容（如输入框），不会被 muted 样式污染 */
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** 删除等危险操作请用 destructive */
  confirmVariant?: "default" | "destructive";
  /** 额外禁用确认按钮（如业务前置条件不满足时） */
  confirmDisabled?: boolean;
  loading?: boolean;
  /** false 时隐藏取消按钮且遮罩不可关闭（用于强引导弹窗） */
  cancellable?: boolean;
  onConfirm: () => void | Promise<void>;
}

/**
 * 轻量确认弹窗（遮罩 + 居中卡片）。无需额外依赖；供删除等高风险操作前二次确认。
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel = "确定",
  cancelLabel = "取消",
  confirmVariant = "default",
  confirmDisabled = false,
  loading = false,
  cancellable = true,
  onConfirm,
}: ConfirmDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-[oklch(0.20_0.025_200/0.4)] backdrop-blur-sm"
        aria-label={cancellable ? cancelLabel : undefined}
        disabled={loading || !cancellable}
        onClick={() => { if (cancellable) onOpenChange(false); }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="bg-card border-border relative z-10 w-full max-w-md rounded-xl border p-6 shadow-xl shadow-foreground/5"
      >
        <h2 id="confirm-dialog-title" className="text-lg font-semibold tracking-tight">
          {title}
        </h2>
        <div className="text-muted-foreground mt-2 text-sm leading-relaxed">{description}</div>
        {children && <div className="mt-4">{children}</div>}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          {cancellable && (
            <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => onOpenChange(false)}>
              <X className="size-4" aria-hidden />
              {cancelLabel}
            </Button>
          )}
          <Button
            type="button"
            variant={confirmVariant === "destructive" ? "destructive" : "default"}
            size="sm"
            disabled={loading || confirmDisabled}
            onClick={() => void onConfirm()}
          >
            <Check className="size-4" aria-hidden />
            {loading ? "处理中…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
