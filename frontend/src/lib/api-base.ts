/** 前端直连 FastAPI 的基地址，与阶段 1 健康检查保持一致。
 *
 * 默认使用 127.0.0.1 而非 localhost：在部分环境下 localhost 会优先解析到 IPv6(::1)，
 * 若后端只监听 IPv4，会导致浏览器 fetch 立刻失败（表现为 Failed to fetch），而人设聊天等同域请求也会受影响。
 */
export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
}
