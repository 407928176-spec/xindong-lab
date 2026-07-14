"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useLlmConfig } from "@/contexts/LlmConfigContext";

/** 这些页面在没配置大模型时也能访问，否则玩家就被锁死在外面了。 */
const CONFIG_FREE_PATHS = ["/setup", "/settings"];

export function SetupGuard({ children }: { children: ReactNode }) {
  const { status } = useLlmConfig();
  const pathname = usePathname();
  const router = useRouter();
  const isConfigFree = CONFIG_FREE_PATHS.includes(pathname);

  useEffect(() => {
    if (status === "unconfigured" && !isConfigFree) {
      router.replace("/setup");
    }
    if (status === "ready" && pathname === "/setup") {
      router.replace("/");
    }
  }, [status, isConfigFree, pathname, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <div className="text-muted-foreground text-sm">加载中…</div>
      </div>
    );
  }

  // 后端没起来时给出可执行的提示，而不是把玩家丢进一个填了也没用的向导。
  if (status === "error") {
    return (
      <div className="flex min-h-dvh items-center justify-center p-4">
        <div className="border-destructive/30 bg-destructive/8 max-w-md space-y-2 rounded-2xl border p-5 text-center">
          <p className="text-foreground text-sm font-medium">连不上后端服务</p>
          <p className="text-muted-foreground text-xs leading-relaxed">
            请确认后端已经启动（默认地址 http://127.0.0.1:8000）。
            如果你是双击启动脚本运行的，看一下那个黑色命令行窗口有没有报错。
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="text-foreground text-xs font-medium underline underline-offset-2"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (status === "unconfigured" && !isConfigFree) {
    return null;
  }

  return <>{children}</>;
}
