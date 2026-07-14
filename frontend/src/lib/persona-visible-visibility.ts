/**
 * 可见层展示规则：隐藏 null / "" / "unknown" / []；
 * initiative_pattern === "unclear" 时不展示该行。
 */

export function isNonemptyScalar(v: unknown): boolean {
  if (v === null || v === undefined) return false;
  if (typeof v !== "string") return false;
  const s = v.trim();
  if (!s) return false;
  if (s === "unknown") return false;
  return true;
}

export function filterStringList(arr: string[] | undefined): string[] {
  if (!arr?.length) return [];
  return arr.filter((x) => isNonemptyScalar(x));
}

export function enumDisplayLabel(
  raw: string | null | undefined,
  map: Record<string, string>,
): string | null {
  if (!isNonemptyScalar(raw)) return null;
  const key = raw!.trim();
  return map[key] ?? key;
}

export function showInitiativePattern(raw: string | null | undefined): boolean {
  if (raw === null || raw === undefined) return false;
  const s = raw.trim();
  if (!s || s === "unknown") return false;
  if (s === "unclear") return false;
  return true;
}
