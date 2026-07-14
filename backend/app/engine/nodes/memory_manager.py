"""步骤 5.5：记忆触发检测（同步、不调用 LLM）。压缩任务见 memory_compression 模块。"""

from __future__ import annotations

from typing import Any

from app.engine.state import ConversationState

# 与 PHASE5_DESIGN §2.3 一致：recent_messages 每条 content 的 Python 字符数之和。
MEMORY_CHAR_THRESHOLD = 10_000


def recent_messages_char_total(state: ConversationState) -> int:
    return sum(len(str(m.get("content", ""))) for m in state.get("recent_messages", []))


def memory_manager(state: ConversationState) -> dict[str, Any]:
    """若近期窗口字符总和达到阈值，标记 should_update_memory；由 API 在 invoke 后入队 BackgroundTasks。"""
    total = recent_messages_char_total(state)
    return {"should_update_memory": total >= MEMORY_CHAR_THRESHOLD}
