/**
 * 模块级单例：在 Next.js 客户端跨页面路由期间持有预热 Promise。
 * 人设确认入库后立刻触发，让用户前往人设库点"开始聊天"时无需等待 LLM 生成 persona_prompt。
 */
const pendingMap = new Map<string, Promise<string>>();

/** 触发后台预热：POST /api/characters，将结果 characterId 缓存在 pendingMap 中。 */
export function prewarmCharacter(personaId: string, apiBase: string): void {
  if (pendingMap.has(personaId)) return;
  const p = fetch(`${apiBase}/api/characters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona_id: personaId }),
  }).then(async (r) => {
    if (!r.ok) throw new Error(`prewarm HTTP ${r.status}`);
    return ((await r.json()) as { id: string }).id;
  });
  pendingMap.set(personaId, p);
  void p.finally(() => pendingMap.delete(personaId));
}

/** 若该 personaId 的预热仍在进行中，返回其 Promise；否则返回 undefined。 */
export function getPendingPrewarm(personaId: string): Promise<string> | undefined {
  return pendingMap.get(personaId);
}
