"use client";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";

interface EmptyPersonaGuideDialogProps {
  open: boolean;
  onConfirm: () => void;
}

export function EmptyPersonaGuideDialog({ open, onConfirm }: EmptyPersonaGuideDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={() => {}}
      title="先创建一个人设吧"
      description="你还没有任何人设。创建一个人设后，才能开始与 TA 聊天。"
      confirmLabel="创建人设"
      cancellable={false}
      onConfirm={onConfirm}
    />
  );
}
