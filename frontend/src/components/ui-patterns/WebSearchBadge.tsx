"use client";

import { Globe } from "lucide-react";

import { useLlmConfig } from "@/contexts/LlmConfigContext";

/**
 * 聊天页的联网搜索状态标识。
 *
 * 联网搜索只有火山方舟支持，玩家换了供应商就用不了。角色答不上「今天天气」时，
 * 这个标识能让玩家立刻明白是能力限制，而不是以为角色坏了。
 */
export function WebSearchBadge() {
  const { config, status } = useLlmConfig();

  if (status !== "ready" || !config) return null;

  const on = config.web_search_supported;

  return (
    <span
      title={
        on
          ? "当前大模型支持联网搜索，角色可以聊实时话题"
          : "当前大模型不支持联网搜索，角色无法获取实时信息（天气、新闻等）。只有火山方舟开通了联网内容插件的模型支持。"
      }
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] leading-none font-medium ${
        on
          ? "border-primary/25 bg-primary/8 text-primary"
          : "border-border text-muted-foreground"
      }`}
    >
      <Globe className="size-3" aria-hidden />
      <span>联网{on ? "已开启" : "不支持"}</span>
    </span>
  );
}
