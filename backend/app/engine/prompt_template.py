"""通用 prompt 占位符：从 ConversationState 生成替换字典，按模板内 `{identifier}` 替换。"""

from __future__ import annotations

import json
import re
from typing import Any

from app.engine.state import ConversationState

# 与 TypedDict 键名对齐；不用 str.format，以免 .md 内 JSON 花括号冲突。
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _value_to_template_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _format_recent_messages(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "暂无当前保留对话。"

    lines: list[str] = []
    for index, message in enumerate(messages, 1):
        role = str(message.get("role") or "unknown")
        content = str(message.get("content") or "")
        round_number = message.get("round_number")
        prefix = f"{index}."
        if round_number is not None:
            prefix += f" 第 {round_number} 轮"
        lines.append(f"{prefix} {role}：{content}")
    return "\n".join(lines)


def build_relationship_context_for_prompt(state: ConversationState) -> str:
    """按现有记忆规则格式化关系上下文：长期记忆 + 当前保留对话窗口。"""
    long_term_memory = (state.get("long_term_memory") or "").strip()
    recent_messages = state.get("recent_messages") or []
    hidden_state = state.get("hidden_state")
    relationship_state_prompt = (state.get("relationship_state_prompt") or "").strip()
    character_reply = (state.get("character_reply") or "").strip()
    state_changes = state.get("state_changes")

    parts = [
        "【上下文组成规则】",
        "当前关系上下文由长期记忆摘要与当前保留对话窗口共同组成：未触发压缩时，当前保留对话窗口就是目前完整对话；压缩完成后，长期记忆摘要承接更早内容，当前保留对话窗口保留最近 20 轮。",
        "",
        "【长期记忆摘要】",
        long_term_memory or "暂无长期记忆摘要。",
        "",
        "【当前保留对话窗口】",
        _format_recent_messages(recent_messages),
        "",
        "【当前关系状态】",
        relationship_state_prompt or "暂无关系状态说明。",
        _value_to_template_str(hidden_state),
        "",
        "【本轮用户消息】",
        _value_to_template_str(state.get("user_message")),
    ]

    if character_reply or state.get("character_no_reply") is not None:
        parts.extend(
            [
                "",
                "【本轮角色回复】",
                character_reply or "（角色本轮无文字回复）",
                f"角色是否选择沉默：{_value_to_template_str(state.get('character_no_reply'))}",
            ]
        )

    if state_changes:
        parts.extend(["", "【本轮状态评估】", _value_to_template_str(state_changes)])

    return "\n".join(parts)


def state_to_replacement_map(state: ConversationState) -> dict[str, str]:
    """把图状态打成字符串字典，键与 ConversationState 字段名一致。

    persisted_* 为持久化回执，不进模板、不扩大日志占位噪音（步骤 5.7）。
    """
    replacements = {
        key: _value_to_template_str(val)
        for key, val in state.items()
        if not key.startswith("persisted_")
    }
    replacements["relationship_context"] = build_relationship_context_for_prompt(state)
    return replacements


def apply_template_placeholders(template: str, replacements: dict[str, str]) -> str:
    """仅替换模板中出现的 `{identifier}`；replacements 缺键时替换为空串。"""

    def _sub(m: re.Match[str]) -> str:
        return replacements.get(m.group(1), "")

    return _PLACEHOLDER_RE.sub(_sub, template)
