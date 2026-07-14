"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { fetchLlmConfig } from "@/lib/llm-config";
import type { LlmConfigStatus } from "@/types/config";

interface LlmConfigContextValue {
  config: LlmConfigStatus | null;
  /** loading：正在问后端；ready：已配置；unconfigured：没配；error：后端连不上 */
  status: "loading" | "ready" | "unconfigured" | "error";
  refresh: () => Promise<void>;
}

const LlmConfigContext = createContext<LlmConfigContextValue | null>(null);

export function LlmConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<LlmConfigStatus | null>(null);
  const [status, setStatus] = useState<LlmConfigContextValue["status"]>("loading");

  const refresh = useCallback(async () => {
    try {
      const cfg = await fetchLlmConfig();
      setConfig(cfg);
      setStatus(cfg.configured ? "ready" : "unconfigured");
    } catch {
      // 区分「没配置」和「后端没起来」很重要：前者该进向导，
      // 后者进了向导也没用，得告诉玩家后端挂了。
      setConfig(null);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <LlmConfigContext.Provider value={{ config, status, refresh }}>{children}</LlmConfigContext.Provider>
  );
}

export function useLlmConfig(): LlmConfigContextValue {
  const ctx = useContext(LlmConfigContext);
  if (!ctx) throw new Error("useLlmConfig must be used within LlmConfigProvider");
  return ctx;
}
