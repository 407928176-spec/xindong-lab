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
    // 桌面端外壳把内容区锁成一屏高且 overflow-hidden，设置页内容（大模型表单 + 本地数据卡片）
    // 一旦超过一屏就会被裁掉、滚不到。这里让根节点成为高度确定、可纵向滚动的容器，
    // 让两块内容作为整体一起滚动。移动端外壳不限高，走整页滚动，此处不受影响。
    <div className="h-full overflow-y-auto pb-8">
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
