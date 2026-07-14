from __future__ import annotations

from app.engine.nodes.memory_manager import (
    MEMORY_CHAR_THRESHOLD,
    memory_manager,
    recent_messages_char_total,
)
from app.engine.state import minimal_conversation_state


def test_recent_messages_char_total_sums_content() -> None:
    state = minimal_conversation_state()
    state["recent_messages"] = [
        {"role": "user", "content": "ab"},
        {"role": "character", "content": "cde"},
    ]
    assert recent_messages_char_total(state) == 5


def test_memory_manager_below_threshold() -> None:
    state = minimal_conversation_state()
    state["recent_messages"] = [{"role": "user", "content": "x" * 9999}]
    assert recent_messages_char_total(state) == 9999
    out = memory_manager(state)
    assert out == {"should_update_memory": False}


def test_memory_manager_at_threshold() -> None:
    state = minimal_conversation_state()
    state["recent_messages"] = [{"role": "user", "content": "x" * MEMORY_CHAR_THRESHOLD}]
    assert recent_messages_char_total(state) == MEMORY_CHAR_THRESHOLD
    out = memory_manager(state)
    assert out == {"should_update_memory": True}


def test_memory_manager_split_messages_reaches_threshold() -> None:
    state = minimal_conversation_state()
    half = MEMORY_CHAR_THRESHOLD // 2
    state["recent_messages"] = [
        {"role": "user", "content": "a" * half},
        {"role": "character", "content": "b" * (MEMORY_CHAR_THRESHOLD - half)},
    ]
    out = memory_manager(state)
    assert out == {"should_update_memory": True}
