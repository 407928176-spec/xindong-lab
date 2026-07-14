import type { PersonaExtractV06 } from "@/types/persona";

/** 与 ``persona_service.iter_persona_chat_sse_lines`` 对齐的 SSE 载荷（节选）。 */
export type PersonaChatStreamPayload =
  | { type: "token"; text: string }
  | { type: "done"; assistant_message: string; extract: PersonaExtractV06 }
  | { type: "error"; httpStatus?: number; detail?: string };

function parseSseBlock(rawBlock: string): PersonaChatStreamPayload | null {
  const line = rawBlock.trim().split("\n").find((l) => l.startsWith("data: "));
  if (!line) return null;
  return JSON.parse(line.slice(6).trimStart()) as PersonaChatStreamPayload;
}

/**
 * 消费 ``POST /api/personas/chat/stream``（text/event-stream）。
 * ``onToken`` 收到增量文本；返回值为末帧 ``done`` 中的完整字段。
 */
export async function consumePersonaChatSse(
  res: Response,
  onToken: (delta: string) => void,
): Promise<{ assistant_message: string; extract: PersonaExtractV06 }> {
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
  let donePayload: { assistant_message: string; extract: PersonaExtractV06 } | null = null;

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
        if (ev.type === "token" && ev.text) {
          onToken(ev.text);
        } else if (ev.type === "done") {
          donePayload = { assistant_message: ev.assistant_message, extract: ev.extract };
        } else if (ev.type === "error") {
          throw new Error(ev.detail ?? "人设创建对话失败");
        }
      }

      if (done) {
        if (buffer.trim()) {
          const ev = parseSseBlock(buffer);
          if (ev) {
            if (ev.type === "token" && ev.text) {
              onToken(ev.text);
            } else if (ev.type === "done") {
              donePayload = { assistant_message: ev.assistant_message, extract: ev.extract };
            } else if (ev.type === "error") {
              throw new Error(ev.detail ?? "人设创建对话失败");
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
