/**
 * 新手引导的「待弹出」标记。
 *
 * 由配置向导（SetupClient）在**首次配置完大模型、即将进入游戏**时埋下，
 * 由 GameGuide 在真正进入游戏页面后消费并清除。
 *
 * 为什么不能只靠 `xindong:guide:seen`「没看过就弹」：seen 存在浏览器里，
 * 跟后端存档是两套东西。玩家清掉游戏数据重新配置、或者之前因为任何原因
 * 已经把引导关掉过一次，seen 都还留在浏览器里，导致「第一次配置完进游戏」
 * 反而不弹。所以配置完成这个动作要显式地把引导请出来。
 */
export const GUIDE_PENDING_STORAGE_KEY = "xindong:guide:pending";

/** 配置向导保存成功后调用：请求下一个游戏内页面弹出新手引导。 */
export function requestGuideOnNextEntry(): void {
  try {
    localStorage.setItem(GUIDE_PENDING_STORAGE_KEY, "1");
  } catch {
    // 隐私模式等写不进去：退回「没看过就弹」的默认行为，不影响配置流程
  }
}
