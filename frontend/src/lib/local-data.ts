/**
 * 本地浏览器数据的统一清理。
 *
 * 游戏把草稿、未读标记、结局数据等散落在多个 localStorage key 里。这些 key 从来没有
 * 统一的清理入口，删了角色也不会被回收，久而久之会残留。设置页的「清空本地数据」
 * 就靠这里。
 *
 * 注意：只清浏览器侧的临时状态，人设 / 角色 / 聊天记录都在后端 SQLite 里，不受影响。
 */

/** 所有由本应用写入的 localStorage key 前缀。 */
const APP_KEY_PREFIXES = ["xd.", "xindong:"];

export function clearLocalGameData(): number {
  if (typeof window === "undefined") return 0;
  let removed = 0;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key && APP_KEY_PREFIXES.some((p) => key.startsWith(p))) {
        keys.push(key);
      }
    }
    // 先收集再删：边遍历边删会让索引错位，漏掉一半。
    for (const key of keys) {
      window.localStorage.removeItem(key);
      removed += 1;
    }
  } catch {
    // 隐私模式下 localStorage 可能不可用，静默处理
  }
  return removed;
}
