"use client";

import { CharacterChatClient } from "@/components/character-chat/CharacterChatClient";
import { CharacterListClient } from "@/components/character-list/CharacterListClient";
import { useIsDesktop } from "@/hooks/use-is-desktop";

interface CharacterDetailSwitchProps {
  id: string;
}

/**
 * 根据视口宽度二选一挂载移动端聊天页或桌面端列表页。
 * 使用条件渲染（而非 CSS hidden）保证 Radix ScrollArea 在挂载时
 * 已处于可见状态，能正确测量 viewport 高度。
 */
export function CharacterDetailSwitch({ id }: CharacterDetailSwitchProps) {
  const isDesktop = useIsDesktop();

  // SSR 和首次客户端 paint 期间不渲染，防止两棵子树同时挂载
  if (isDesktop === null) return null;

  if (isDesktop) {
    return <CharacterListClient initialSelectedCharacterId={id} />;
  }

  return (
    <CharacterChatClient
      characterId={id}
      returnHref="/"
      returnLabel="首页"
    />
  );
}
