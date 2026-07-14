"""当轮 LLM 输入的 token 估算与 recent_messages 副本截断（PHASE5_DESIGN §2.3、§2.4）。

仅修改传入模型的 messages **副本**；不得删库或改 DB 中的 Message。
recent 从最旧一条开始丢弃，直至总 token 低于上限（可能打断最旧端成对关系，语义固定在此）。
"""

from __future__ import annotations

import functools
import json
from typing import Any

import tiktoken

from app.engine.state import ConversationState, HiddenState

# Doubao 128K 量级；预留输出（§2.4 约 2000 tokens 给生成）
_MAX_CONTEXT_TOKENS = int(128_000 * 0.88)
_OUTPUT_RESERVE = 2_000


@functools.lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoding().encode(text))


def estimate_message_dict(m: dict[str, Any]) -> int:
    role = str(m.get("role", ""))
    content = m.get("content")
    if isinstance(content, list):
        n = 4 + estimate_tokens(role)
        for part in content:
            if not isinstance(part, dict):
                continue
            pt = part.get("type")
            if pt == "text":
                n += estimate_tokens(str(part.get("text", "")))
            elif pt == "image_url":
                n += 1200
            elif pt == "file":
                n += 2500
            else:
                n += 50
        return n
    return 4 + estimate_tokens(role) + estimate_tokens(str(content or ""))


def _role_for_openai_chat(role: str) -> str:
    """OpenAI 兼容接口要求角色侧为 assistant；库内与 API 统一用 character。"""
    r = (role or "").strip()
    if r == "character":
        return "assistant"
    return r


def build_messages_phase52(
    *,
    system_prompt: str,
    persona_prompt: str,
    hidden_state: HiddenState,
    relationship_state_prompt: str,
    long_term_memory: str,
    recent_messages: list[dict[str, Any]],
    user_message: str,
    user_llm_content: str | list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """按 PHASE5 §2.2 顺序组装 messages（未截断 recent 副本）。"""
    tail_user_content: str | list[dict[str, Any]] = (
        user_llm_content if user_llm_content is not None else user_message
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": persona_prompt},
        {
            "role": "system",
            "content": "当前关系状态：" + json.dumps(hidden_state, ensure_ascii=False) + "\n" + relationship_state_prompt,
        },
        {"role": "system", "content": "长期记忆：" + long_term_memory},
        *[{"role": _role_for_openai_chat(str(m["role"])), "content": m["content"]} for m in recent_messages],
        {"role": "user", "content": tail_user_content},
    ]


def truncate_messages_for_context_budget(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """前 4 条 system + 最后 1 条 user 固定；仅缩小中间 recent 段（从最早一条起删）。"""
    if len(messages) < 6:
        return list(messages)

    prefix = messages[:4]
    suffix_user = messages[-1]
    middle = list(messages[4:-1])
    cap = _MAX_CONTEXT_TOKENS - _OUTPUT_RESERVE

    def total(ms: list[dict[str, Any]]) -> int:
        return sum(estimate_message_dict(m) for m in ms)

    while middle and total(prefix + middle + [suffix_user]) > cap:
        middle.pop(0)

    return prefix + middle + [suffix_user]


def build_truncated_llm_messages(state: ConversationState, system_prompt_file_text: str) -> list[dict[str, Any]]:
    """供 generate_reply：system 用文件正文；其余来自 state；返回已截断副本。"""
    user_llm_content = state.get("user_llm_content")
    raw = build_messages_phase52(
        system_prompt=system_prompt_file_text,
        persona_prompt=state["persona_prompt"],
        hidden_state=state["hidden_state"],
        relationship_state_prompt=state.get("relationship_state_prompt", ""),
        long_term_memory=state["long_term_memory"],
        recent_messages=list(state["recent_messages"]),
        user_message=state["user_message"],
        user_llm_content=user_llm_content,
    )
    return truncate_messages_for_context_budget(raw)
