import { apiJson } from "@/lib/api-client";
import type { LlmConfigInput, LlmConfigStatus, LlmProbeResponse } from "@/types/config";

/** 常用供应商预设，让玩家点一下就填好 Base URL，不用去翻文档。 */
export interface ProviderPreset {
  name: string;
  baseUrl: string;
  modelHint: string;
  /** 是否支持联网搜索（仅火山方舟）。 */
  webSearch: boolean;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    name: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    modelHint: "例如 gpt-4o",
    webSearch: false,
  },
  {
    name: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    modelHint: "例如 deepseek-chat",
    webSearch: false,
  },
  {
    name: "火山方舟",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    modelHint: "填推理接入点 ID，例如 ep-2024...",
    webSearch: true,
  },
  {
    name: "Ollama（本地）",
    baseUrl: "http://localhost:11434/v1",
    modelHint: "例如 qwen2.5:14b",
    webSearch: false,
  },
];

export function fetchLlmConfig(): Promise<LlmConfigStatus> {
  return apiJson<LlmConfigStatus>("/api/config/llm");
}

export function testLlmConfig(input: LlmConfigInput): Promise<LlmProbeResponse> {
  return apiJson<LlmProbeResponse>("/api/config/llm/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function saveLlmConfig(input: LlmConfigInput): Promise<LlmConfigStatus> {
  return apiJson<LlmConfigStatus>("/api/config/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** 联网搜索的能力说明。向导和设置页共用，避免两处文案讲不一样的话。 */
export const WEB_SEARCH_NOTICE =
  "联网搜索只有火山方舟（Volcengine Ark）开通了「联网内容插件」的模型支持。" +
  "使用 OpenAI、DeepSeek、本地模型等其他供应商时，角色无法获取实时信息（天气、新闻等），其余玩法不受影响。";
