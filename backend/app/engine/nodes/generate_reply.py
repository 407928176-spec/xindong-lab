"""步骤 5.3：按 PHASE5 §2.2 组装 messages，副本截断后调用豆包，写入 character_reply。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from app.engine.llm_client import call_llm
from app.engine.message_token_budget import build_truncated_llm_messages
from app.engine.no_reply import normalize_character_reply
from app.engine.prompts.loader import read_prompt
from app.engine.state import ConversationState
from app.engine.web_context import build_web_context, decide_web_context, insert_web_context_message

logger = logging.getLogger(__name__)


def _messages_for_reply(state: ConversationState) -> tuple[str, list[dict[str, Any]]]:
    system_text = read_prompt("system_prompt.md")
    if not system_text.strip():
        logger.warning("generate_reply: system_prompt.md empty or missing")
    messages = build_truncated_llm_messages(state, system_text)
    decision = decide_web_context(state)
    web_context = build_web_context(state, decision)
    messages = insert_web_context_message(messages, web_context)
    return system_text, messages


def stream_character_reply_tokens(state: ConversationState) -> Iterator[str]:
    """与 generate_reply 相同组装；以 LLM 流式增量产出 token（供 SSE 管道）。"""
    _unused, messages = _messages_for_reply(state)
    stream = call_llm(messages, temperature=0.8, stream=True, use_web_search=False)
    if isinstance(stream, str):
        yield stream
        return
    yield from stream


def generate_reply(state: ConversationState) -> dict[str, Any]:
    _unused, messages = _messages_for_reply(state)
    reply = call_llm(messages, temperature=0.8, stream=False, use_web_search=False)
    assert isinstance(reply, str)
    text, no_reply = normalize_character_reply(reply)
    return {"character_reply": text, "character_no_reply": no_reply}
