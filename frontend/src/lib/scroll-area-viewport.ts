/** Base UI ScrollArea：`scrollIntoView` 往往滚不动内部 Viewport，改为直接设 `scrollTop`（与 CharacterChatClient 注释一致）。 */

export function getScrollAreaViewport(bottomAnchor: HTMLElement | null): HTMLElement | null {
  if (!bottomAnchor) return null;
  return bottomAnchor.closest('[data-slot="scroll-area-viewport"]') as HTMLElement | null;
}

/** 将滚动区滚到底部；成功返回 true。 */
export function scrollScrollAreaViewportToBottom(bottomAnchor: HTMLElement | null): boolean {
  const viewport = getScrollAreaViewport(bottomAnchor);
  if (!viewport) return false;
  viewport.scrollTop = viewport.scrollHeight;
  return true;
}
