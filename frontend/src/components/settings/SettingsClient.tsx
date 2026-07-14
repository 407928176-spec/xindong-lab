"use client";

import { useCallback, useState } from "react";
import { Trash2 } from "lucide-react";

import { SetupClient } from "@/components/setup/SetupClient";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { clearLocalGameData } from "@/lib/local-data";

export function SettingsClient() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);

  const handleClear = useCallback(() => {
    setCleared(clearLocalGameData());
    setConfirmOpen(false);
  }, []);

  return (
    <div className="pb-8">
      <SetupClient mode="settings" />

      <div className="mx-auto w-full max-w-lg px-4">
        <section className="border-border bg-card/60 rounded-3xl border p-5">
          <h2 className="text-sm font-medium">本地数据</h2>
          <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
            清空浏览器里保存的输入草稿、未读标记和结局展示状态。
            人设、角色和聊天记录都存在本机数据库里，不会被删除。
          </p>
          {cleared !== null && (
            <p className="text-muted-foreground mt-2 text-xs" role="status">
              ✅ 已清理 {cleared} 项本地缓存
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 className="size-4" aria-hidden />
            清空本地数据
          </Button>
        </section>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="清空本地数据？"
        description="会清掉未发送的输入草稿、未读标记和结局展示状态。人设、角色和聊天记录不受影响。"
        confirmLabel="清空"
        cancelLabel="取消"
        onConfirm={handleClear}
      />
    </div>
  );
}
