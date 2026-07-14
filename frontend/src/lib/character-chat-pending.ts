/**
 * 跨路由存活的模块级单例，追踪角色聊天的进行中请求。
 * 解决：用户发消息后离开聊天页，重新进入时能看到自己发的文本和「对方正在输入中」提示。
 */

import type { CharacterChatResponse } from "@/types/character";

interface PendingChat {
  userTempId: string;
  userContent: string;
  attachmentIds: string[];
  promise: Promise<CharacterChatResponse>;
}

interface PendingPreviewRecord {
  content: string;
  createdAt: number;
}

// 每个角色最多同时一个进行中请求
const pendingMap = new Map<string, PendingChat>();

// 当前处于活跃状态的聊天页计数（同一角色可能同时存在隐藏移动页和桌面嵌入页）。
const activeChatPageCounts = new Map<string, number>();

/** 注册当前聊天页为活跃，返回 cleanup 函数供 useEffect return */
export function registerActiveChatPage(id: string): () => void {
  activeChatPageCounts.set(id, (activeChatPageCounts.get(id) ?? 0) + 1);
  return () => {
    const next = (activeChatPageCounts.get(id) ?? 0) - 1;
    if (next > 0) {
      activeChatPageCounts.set(id, next);
    } else {
      activeChatPageCounts.delete(id);
    }
  };
}

/** 检查指定角色的聊天页是否当前处于活跃状态 */
export function isActiveChatPage(id: string): boolean {
  return (activeChatPageCounts.get(id) ?? 0) > 0;
}

export function setPendingChat(id: string, chat: PendingChat): void {
  pendingMap.set(id, chat);
}

export function getPendingChat(id: string): PendingChat | undefined {
  return pendingMap.get(id);
}

export function clearPendingChat(id: string): void {
  pendingMap.delete(id);
}

export function notifyCharactersChanged(characterId?: string): void {
  window.dispatchEvent(new CustomEvent("xd:characters-changed", { detail: { characterId } }));
}

/** 在用户消息落库前，把待展示预览文本暂存到 localStorage，供列表页乐观展示。 */
export function setPendingPreview(id: string, content: string, createdAt: number = Date.now()): void {
  try {
    localStorage.setItem(`xd.pendingPreview.${id}`, JSON.stringify({ content, createdAt } satisfies PendingPreviewRecord));
  } catch {}
}

export function clearPendingPreview(id: string): void {
  try { localStorage.removeItem(`xd.pendingPreview.${id}`); } catch {}
}

export function getPendingPreviewRecord(id: string): PendingPreviewRecord | null {
  try {
    const raw = localStorage.getItem(`xd.pendingPreview.${id}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PendingPreviewRecord | string;
    if (typeof parsed === "string") {
      return { content: parsed, createdAt: 0 };
    }
    if (typeof parsed?.content === "string" && typeof parsed?.createdAt === "number") {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

/** 返回 null 表示无待展示预览。 */
export function getPendingPreview(id: string): string | null {
  return getPendingPreviewRecord(id)?.content ?? null;
}
