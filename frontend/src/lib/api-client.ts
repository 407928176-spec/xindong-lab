import { getApiBaseUrl } from "@/lib/api-base";

export type ApiClientOptions = RequestInit;

export async function apiFetch(path: string, opts: ApiClientOptions = {}): Promise<Response> {
  // 单机游戏没有账号，不需要注入任何鉴权头。
  return fetch(`${getApiBaseUrl()}${path}`, opts);
}

export async function apiJson<T>(path: string, opts: ApiClientOptions = {}): Promise<T> {
  const res = await apiFetch(path, opts);
  if (!res.ok) {
    const text = await res.text();
    try {
      const json = JSON.parse(text);
      if (json && typeof json.detail === "string") {
        throw new Error(json.detail);
      }
      if (Array.isArray(json?.detail)) {
        const messages = json.detail
          .map((item: unknown) => {
            if (item && typeof item === "object" && typeof (item as { msg?: unknown }).msg === "string") {
              return (item as { msg: string }).msg.replace(/^Value error,\s*/, "");
            }
            return null;
          })
          .filter((m: string | null): m is string => Boolean(m));
        if (messages.length > 0) throw new Error(messages.join("；"));
      }
    } catch (e) {
      if (e instanceof SyntaxError) {
        // 非 JSON 响应，直接用原文
      } else {
        throw e;
      }
    }
    throw new Error(text);
  }
  return res.json() as Promise<T>;
}
