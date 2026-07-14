from __future__ import annotations

from typing import cast

from app.engine.prompt_template import build_relationship_context_for_prompt, state_to_replacement_map
from app.engine.state import ConversationState, minimal_conversation_state


def test_state_to_replacement_map_excludes_persisted_prefix() -> None:
    base = minimal_conversation_state()
    merged = cast(
        ConversationState,
        {
            **base,
            "persisted_round": 9,
            "persisted_user_message_id": "u-1",
            "persisted_noise": "x",
        },
    )
    m = state_to_replacement_map(merged)
    assert "persisted_round" not in m
    assert "persisted_user_message_id" not in m
    assert "user_message" in m
    assert "relationship_context" in m


def test_relationship_context_uses_full_current_messages_without_summary() -> None:
    state = minimal_conversation_state()
    state["long_term_memory"] = ""
    state["relationship_state_prompt"] = "当前关系仍在观察阶段。"
    state["recent_messages"] = [
        {"role": "user", "content": "你好", "round_number": 1},
        {"role": "character", "content": "你好呀", "round_number": 1},
        {"role": "user", "content": "我们慢慢聊", "round_number": 2},
    ]
    state["user_message"] = "今天继续聊聊"

    context = build_relationship_context_for_prompt(state)

    assert "暂无长期记忆摘要" in context
    assert "未触发压缩时，当前保留对话窗口就是目前完整对话" in context
    assert "压缩完成后，长期记忆摘要承接更早内容，当前保留对话窗口保留最近 20 轮" in context
    assert "第 1 轮 user：你好" in context
    assert "第 2 轮 user：我们慢慢聊" in context
    assert "今天继续聊聊" in context


def test_relationship_context_combines_summary_recent_messages_and_state_changes() -> None:
    state = minimal_conversation_state()
    state["long_term_memory"] = "更早的关系摘要"
    state["recent_messages"] = [{"role": "character", "content": "最近的回应", "round_number": 21}]
    state["character_reply"] = "本轮角色回复"
    state["state_changes"] = {
        "comfort_delta": -1,
        "interest_delta": 0,
        "trust_delta": -2,
        "alertness_delta": 2,
        "reason": "本轮互动让关系退后",
    }

    context = build_relationship_context_for_prompt(state)

    assert "更早的关系摘要" in context
    assert "第 21 轮 character：最近的回应" in context
    assert "本轮角色回复" in context
    assert "本轮互动让关系退后" in context
