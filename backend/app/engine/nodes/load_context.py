"""从 DB 与文件装配对话上下文（步骤 5.2）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine.attachment_processing import (
    assemble_user_llm_content_list,
    process_attachment_ids_for_llm,
)
from app.engine.no_reply import recent_dict_from_message
from app.engine.prompts.loader import read_prompt
from app.engine.state import ConversationState, HiddenState
from app.db.session import SessionLocal
from app.models.character import Character
from app.models.enums import AttachmentScene, MessageRole
from app.models.message import Message
from app.models.persona import Persona

logger = logging.getLogger(__name__)


def user_message_count(db: Session, character_id: str) -> int:
    """与 current_round 一致：该角色下 user 角色消息条数（步骤 5.7 persisted_round 事实源）。"""
    cid = (character_id or "").strip()
    if not cid:
        return 0
    n = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.character_id == cid,
            Message.role == MessageRole.USER.value,
        )
    )
    return int(n or 0)


def _default_hidden_state() -> HiddenState:
    return {
        "comfort": 50.0,
        "interest": 50.0,
        "trust": 50.0,
        "alertness": 50.0,
        "baseline_compatibility": 50.0,
    }


def _coerce_hidden_state(raw: dict[str, Any] | None) -> HiddenState:
    if not raw:
        return _default_hidden_state()
    base = _default_hidden_state()
    for k in base:
        if k in raw and isinstance(raw[k], (int, float)):
            base[k] = float(raw[k])
    return base


def _band(value: float) -> str:
    if value < 40:
        return "低"
    if value < 65:
        return "中"
    return "高"


def build_relationship_state_prompt(hidden: HiddenState) -> str:
    comfort = float(hidden["comfort"])
    interest = float(hidden["interest"])
    trust = float(hidden["trust"])
    alertness = float(hidden["alertness"])
    baseline = float(hidden["baseline_compatibility"])

    lines = [
        "【当前关系状态·系统内部】",
        f"舒适感{_band(comfort)}、兴趣度{_band(interest)}、信任感{_band(trust)}、警惕度{_band(alertness)}、基础契合度{_band(baseline)}。",
    ]

    if alertness >= 70 or trust < 40 or comfort < 40:
        lines.append("当前应明显保留边界，避免快速确认关系；面对表白更倾向于拒绝、拖缓或要求慢下来。")
    elif comfort >= 70 and interest >= 70 and trust >= 60 and alertness <= 35:
        lines.append("当前关系已明显升温，可以更主动、更亲近；面对自然表白更容易默认接受，也可以在合适语境下主动确认关系。")
    elif interest >= 65 and comfort >= 55 and alertness < 55:
        lines.append("当前有正向好感，可以表现出暧昧、主动接话和轻微推进，但未必立即确认关系。")
    else:
        lines.append("当前关系仍在观察和试探阶段，保持自然互动，不要突然越级确认关系。")

    if baseline >= 70:
        lines.append("同样的正向互动更容易被理解为合拍和有吸引力。")
    elif baseline < 40:
        lines.append("同样的互动更难快速升温，需要更多稳定和尊重边界的表现。")

    return "\n".join(lines)


def _build_persona_prompt(persona: Persona) -> str:
    """将人设表字段拼成一段供 LLM 使用的角色层文本（非 DB 新列）。"""
    parts = [
        f"【称呼】{persona.display_name}",
        f"【身份概要】{persona.identity_summary}",
        f"【性格】{persona.personality_summary}",
        f"【兴趣】{persona.interests}",
        f"【聊天风格】{persona.chat_style}",
        f"【背景（可见）】{persona.visible_background}",
        "【系统隐藏层·初始倾向】",
        persona.hidden_initial_tendency,
        "【系统隐藏层·印象基线】",
        persona.hidden_impression_baseline,
        "【系统隐藏层·关键判断】",
        persona.hidden_key_judgment,
        "【系统隐藏层·节奏容忍】",
        persona.hidden_pacing_tolerance,
        "【系统隐藏层·敏感点】",
        persona.hidden_sensitivity_points,
    ]
    return "\n".join(p.strip() for p in parts if str(p).strip())


def load_context_from_db(db: Session, state: ConversationState) -> dict[str, Any]:
    """从已打开的 Session 加载上下文字段；供节点与单测复用。"""
    character_id = (state.get("character_id") or "").strip()
    if not character_id:
        logger.warning("load_context: empty character_id, skipping DB load")
        return {}

    character = db.get(Character, character_id)
    if character is None:
        logger.warning("load_context: character_id=%s not found, skipping DB load", character_id)
        return {}

    persona = db.get(Persona, character.persona_id)
    if persona is None:
        logger.warning("load_context: persona missing for character_id=%s", character_id)
        return {}

    msg_stmt = (
        select(Message)
        .where(Message.character_id == character_id)
        .order_by(Message.created_at.asc(), Message.round_number.asc())
    )
    messages = list(db.scalars(msg_stmt))

    recent_messages: list[dict[str, Any]] = []
    for m in messages:
        recent_messages.append(recent_dict_from_message(m))

    current_round = user_message_count(db, character_id)

    anon = (state.get("anon_user_id") or "").strip()
    pending_ids = state.get("pending_attachment_ids") or []
    user_text = (state.get("user_message") or "").strip()
    user_llm_content: str | list[dict[str, Any]] | None = None
    if pending_ids:
        if anon:
            try:
                outcome = process_attachment_ids_for_llm(
                    db,
                    list(pending_ids),
                    anon_user_id=anon,
                    scene=AttachmentScene.CHARACTER_CHAT.value,
                    conversation_id=character_id,
                    character_id=character_id,
                )
                user_llm_content = assemble_user_llm_content_list(user_text, outcome)
            except Exception as exc:
                logger.warning("load_context: pending attachment processing failed: %s", type(exc).__name__)
        else:
            logger.warning("load_context: pending_attachment_ids set but anon_user_id missing")

    if not character.persona_prompt:
        persona_text = _build_persona_prompt(persona)
    else:
        persona_text = character.persona_prompt

    system_text = read_prompt("system_prompt.md")
    if not system_text:
        logger.warning("load_context: system_prompt.md empty or missing")

    hidden_state = _coerce_hidden_state(character.hidden_state_snapshot)
    out = {
        "system_prompt": system_text,
        "persona_prompt": persona_text,
        "hidden_state": hidden_state,
        "relationship_state_prompt": build_relationship_state_prompt(hidden_state),
        "long_term_memory": (character.long_term_memory or "").strip(),
        "recent_messages": recent_messages,
        "current_round": current_round,
    }
    if user_llm_content is not None:
        out["user_llm_content"] = user_llm_content
    return out


def load_context(state: ConversationState) -> dict[str, Any]:
    """LangGraph 节点：打开短生命周期 DB 会话并合并上下文。"""
    db = SessionLocal()
    try:
        return load_context_from_db(db, state)
    finally:
        db.close()
