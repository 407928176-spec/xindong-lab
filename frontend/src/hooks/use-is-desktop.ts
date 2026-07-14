"use client";

import { useEffect, useState } from "react";

/**
 * 返回当前视口是否为桌面宽度（≥1024px）。
 * 初始值为 null，在首次挂载后同步更新。
 * null 可用于避免 SSR/客户端首次渲染的双挂载闪烁。
 */
export function useIsDesktop(): boolean | null {
  const [isDesktop, setIsDesktop] = useState<boolean | null>(null);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const sync = (): void => setIsDesktop(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  return isDesktop;
}
