/**
 * 角色聊天输入框草稿持久化：用户输入内容但未发送即退出/切换角色时，
 * 把内容写入 localStorage，下次进入聊天页自动恢复；列表页用淡红色字显示。
 */

const KEY = (id: string) => `xd.draft.${id}`;
const EVENT = "xd:draft-changed";

export function getDraft(id: string): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(KEY(id)) ?? "";
  } catch {
    return "";
  }
}

export function setDraft(id: string, text: string): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = text.trim();
    if (trimmed) {
      localStorage.setItem(KEY(id), text);
    } else {
      localStorage.removeItem(KEY(id));
    }
    window.dispatchEvent(new CustomEvent(EVENT, { detail: { id } }));
  } catch {
    // localStorage 不可用时静默失败
  }
}

export function clearDraft(id: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(KEY(id));
    window.dispatchEvent(new CustomEvent(EVENT, { detail: { id } }));
  } catch {
    // 静默失败
  }
}

export const DRAFT_CHANGED_EVENT = EVENT;
