"""步骤 5.7：本轮双消息落库、角色快照与终局标记；回传 persisted_* 供 API 组装（不经「查最新两条」）。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.engine.nodes.load_context import user_message_count
from app.engine.state import ConversationState
from app.models.character import Character
from app.models.ending import Ending
from app.models.enums import CharacterStatus, MessageRole
from app.models.message import Message

logger = logging.getLogger(__name__)


def _save_turn_with_session(db: Session, state: ConversationState) -> dict[str, Any]:
    cid = (state.get("character_id") or "").strip()
    if not cid:
        logger.warning("save_and_respond: empty character_id, skip")
        return {}

    character = db.get(Character, cid)
    if character is None:
        logger.warning("save_and_respond: character not found id=%s, skip", cid)
        return {}

    # 与 load_context.current_round 一致：已有 user 条数；本轮写入后即为 persisted_round。
    current_round = user_message_count(db, cid)
    persisted_round = current_round + 1

    user_text = (state.get("user_message") or "").strip()
    char_reply = (state.get("character_reply") or "").strip()
    char_no_reply = bool(state.get("character_no_reply"))

    user_msg = Message(
        character_id=cid,
        role=MessageRole.USER.value,
        content=user_text,
        round_number=persisted_round,
    )
    char_msg = Message(
        character_id=cid,
        role=MessageRole.CHARACTER.value,
        content=char_reply,
        round_number=persisted_round,
        internal_phase_change={"no_reply": True} if char_no_reply else None,
    )
    db.add(user_msg)
    db.add(char_msg)

    new_hidden = state.get("new_hidden_state")
    if isinstance(new_hidden, dict):
        character.hidden_state_snapshot = new_hidden

    hb = int(round(float(state.get("new_heartbeat_score", 50.0))))
    character.heartbeat_score = hb

    ending = (state.get("ending_result") or "").strip()
    if ending:
        character.is_ended = True
        # 只要本轮写入终局记录，就先落到 ENDING_UNREAD；
        # 用户查看终局后再通过 acknowledge-ending 移入缘散录。
        character.status = CharacterStatus.ENDING_UNREAD.value
        ending_row = character.ending
        if ending_row is None:
            ending_row = Ending(character_id=cid)
            db.add(ending_row)
        ending_row.ending_kind = ending
        ending_row.content = (state.get("ending_evaluation") or "").strip()
        ending_row.user_review = (state.get("user_review") or "").strip() or None

    character.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user_msg)
    db.refresh(char_msg)
    db.refresh(character)

    return {
        "persisted_user_message_id": user_msg.id,
        "persisted_assistant_message_id": char_msg.id,
        "persisted_round": persisted_round,
        "persisted_heartbeat_score": hb,
        "persisted_user_message_at": user_msg.created_at,
        "persisted_assistant_message_at": char_msg.created_at,
    }


def save_and_respond(state: ConversationState) -> dict[str, Any]:
    """使用独立 Session 提交；与路由层 get_db 非同一事务（MVP 技术债）。

    同角色并发请求可能读到相同 user_message_count，从而得到相同 persisted_round（技术债：
    后续可选 per-character 锁或 DB 唯一约束 + 重试）。
    """
    db = SessionLocal()
    try:
        return _save_turn_with_session(db, state)
    except Exception:
        logger.exception("save_and_respond: failed character_id=%s", state.get("character_id"))
        db.rollback()
        raise
    finally:
        db.close()
