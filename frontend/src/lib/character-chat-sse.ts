import type { CharacterChatResponse } from "@/types/character";

export type CharacterChatStreamPayload =
  | { type: "assistant_done"; text: string; is_no_reply?: boolean }
  | { type: "ending_pending" }
  | ({ type: "done" } & CharacterChatResponse)
  | { type: "error"; httpStatus?: number; detail?: string };

function parseSseBlock(rawBlock: string): CharacterChatStreamPayload | null {
  const line = rawBlock.trim().split("\n").find((l) => l.startsWith("data: "));
  if (!line) return null;
  return JSON.parse(line.slice(6).trimStart()) as CharacterChatStreamPayload;
}

interface CharacterChatSseHandlers {
  onAssistantDone?: (text: string) => void;
  onEndingPending?: () => void;
}

export async function consumeCharacterChatSse(
  res: Response,
  handlers: CharacterChatSseHandlers = {},
): Promise<CharacterChatResponse> {
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const msg =
      typeof detail?.detail === "string"
        ? detail.detail
        : `请求失败（HTTP ${res.status}）`;
    throw new Error(msg);
  }

  const body = res.body;
  if (!body) {
    throw new Error("响应无正文");
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: CharacterChatResponse | null = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) >= 0) {
        const rawBlock = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const ev = parseSseBlock(rawBlock);
        if (!ev) continue;
        if (ev.type === "assistant_done") {
          handlers.onAssistantDone?.(ev.text);
        } else if (ev.type === "ending_pending") {
          handlers.onEndingPending?.();
        } else if (ev.type === "done") {
          donePayload = ev;
        } else if (ev.type === "error") {
          throw new Error(ev.detail ?? "角色对话失败");
        }
      }

      if (done) {
        if (buffer.trim()) {
          const ev = parseSseBlock(buffer);
          if (ev) {
            if (ev.type === "assistant_done") {
              handlers.onAssistantDone?.(ev.text);
            } else if (ev.type === "ending_pending") {
              handlers.onEndingPending?.();
            } else if (ev.type === "done") {
              donePayload = ev;
            } else if (ev.type === "error") {
              throw new Error(ev.detail ?? "角色对话失败");
            }
          }
        }
        break;
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* ignore */
    }
  }

  if (!donePayload) {
    throw new Error("流式响应未返回完整结果");
  }

  return donePayload;
}
