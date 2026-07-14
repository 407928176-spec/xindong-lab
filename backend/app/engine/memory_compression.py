"""步骤 5.5：长记忆异步压缩任务（供 FastAPI BackgroundTasks 调用，不在 LangGraph 节点内 await）。"""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.engine.llm_client import call_llm, get_summary_model
from app.engine.no_reply import recent_dict_from_message
from app.engine.prompt_template import apply_template_placeholders, state_to_replacement_map
from app.engine.prompts.loader import read_prompt
from app.engine.state import ConversationState, minimal_conversation_state
from app.models.character import Character
from app.models.enums import MessageRole
from app.models.message import Message

logger = logging.getLogger(__name__)

PAIR_KEEP = 20

# 同一 character 串行压缩，避免并发写 DB 撕裂（MVP：进程内 Lock；持锁失败则跳过本次）。
_compression_locks: dict[str, threading.Lock] = {}
_lock_registry_guard = threading.Lock()


def _lock_for_character(character_id: str) -> threading.Lock:
    with _lock_registry_guard:
        if character_id not in _compression_locks:
            _compression_locks[character_id] = threading.Lock()
        return _compression_locks[character_id]


def _messages_to_recent_dicts(messages: list[Message]) -> list[dict[str, Any]]:
    """与 load_context 一致：沉默轮用占位句 + is_no_reply。"""
    return [recent_dict_from_message(m) for m in messages]


def collect_message_ids_to_keep_last_n_pairs(messages: list[Message], n_pairs: int) -> set[str]:
    """顺扫时间升序列表：相邻 user→character 为一对。

    仅保留**最后 n_pairs 对**共 2*n_pairs 条消息的 id；其余（含首部不成对、中部错位、尾部单独 user）均不进入 keep，后续可被删除。
    §2.3：末尾仅半条 user 无 character 回复成对时，该条不参与「一轮」计数，随旧消息删除。
    """
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(messages):
        cur = messages[i]
        nxt = messages[i + 1] if i + 1 < len(messages) else None
        if (
            cur.role == MessageRole.USER.value
            and nxt is not None
            and nxt.role == MessageRole.CHARACTER.value
        ):
            pairs.append((cur.id, nxt.id))
            i += 2
        else:
            i += 1

    if not pairs:
        # 无法识别任何完整对：不裁剪，避免误删
        return {m.id for m in messages}

    tail = pairs[-n_pairs:]
    keep: set[str] = set()
    for uid, aid in tail:
        keep.add(uid)
        keep.add(aid)
    return keep


def _build_state_for_template(character_id: str, long_term_memory: str, recent_messages: list[dict[str, Any]]) -> ConversationState:
    base = minimal_conversation_state()
    base["character_id"] = character_id
    base["long_term_memory"] = long_term_memory
    base["recent_messages"] = recent_messages
    return base


def run_long_memory_compression_job(character_id: str, user_id: str | None = None) -> None:
    """读 DB → 摘要 LLM → 写 long_term_memory → 仅保留最近 PAIR_KEEP 轮成对消息。

    关键：读完数据后立即关闭第一个 session，在不持有任何 DB 连接的情况下执行摘要 LLM 调用
    （该调用可能阻塞十几秒），写入时再开第二个 session。避免长时间占住连接池槽位。
    """
    cid = (character_id or "").strip()
    if not cid:
        logger.warning("memory_compression: empty character_id")
        return

    lock = _lock_for_character(cid)
    if not lock.acquire(blocking=False):
        logger.warning("memory_compression: skip character_id=%s (compression already running)", cid)
        return

    try:
        # ── 第一阶段：读取数据，随后立即释放连接 ──────────────────────────────
        user_content: str = ""
        delete_ids: list[str] = []
        keep_count: int = 0
        try:
            db = SessionLocal()
            try:
                character = db.get(Character, cid)
                if character is None:
                    logger.warning("memory_compression: character not found id=%s", cid)
                    return

                stmt = (
                    select(Message)
                    .where(Message.character_id == cid)
                    .order_by(Message.created_at.asc(), Message.round_number.asc())
                )
                messages = list(db.scalars(stmt))

                recent_dicts = _messages_to_recent_dicts(messages)
                state = _build_state_for_template(cid, (character.long_term_memory or "").strip(), recent_dicts)

                template = read_prompt("memory_summary_prompt.md")
                user_content = apply_template_placeholders(template, state_to_replacement_map(state))

                keep_ids = collect_message_ids_to_keep_last_n_pairs(messages, PAIR_KEEP)
                keep_count = len(keep_ids)
                delete_ids = [m.id for m in messages if m.id not in keep_ids]
            finally:
                # 连接归还连接池，后续 LLM 调用期间不再占用 DB 连接
                db.close()
        except Exception:
            logger.exception("memory_compression: read phase failed character_id=%s", cid)
            return

        if not user_content.strip():
            logger.warning("memory_compression: empty template after read/replace, skip LLM and DB trim")
            return

        # ── 第二阶段：摘要 LLM 调用（不持有任何 DB 连接）──────────────────────
        try:
            new_summary = call_llm(
                [{"role": "user", "content": user_content}],
                temperature=0.4,
                stream=False,
                model=get_summary_model(),
                use_auxiliary_credentials=True,
            )
            assert isinstance(new_summary, str)
        except Exception:
            logger.exception("memory_compression: LLM phase failed character_id=%s", cid)
            return

        # ── 第三阶段：写入摘要并删除旧消息，重新开 session ──────────────────────
        try:
            db = SessionLocal()
            try:
                character = db.get(Character, cid)
                if character is None:
                    logger.warning("memory_compression: character disappeared before write id=%s", cid)
                    return
                character.long_term_memory = new_summary.strip()
                if delete_ids:
                    db.execute(delete(Message).where(Message.id.in_(delete_ids)))
                db.commit()
                logger.info(
                    "memory_compression: done character_id=%s kept=%s deleted=%s",
                    cid,
                    keep_count,
                    len(delete_ids),
                )
            except Exception:
                logger.exception("memory_compression: write phase failed character_id=%s", cid)
                db.rollback()
            finally:
                db.close()
        except Exception:
            logger.exception("memory_compression: write session setup failed character_id=%s", cid)
    finally:
        lock.release()


def enqueue_long_memory_compression_after_graph(
    state: ConversationState,
    background_tasks: BackgroundTasks | None,
) -> None:
    """在整图 invoke 完成后由 API 调用：若本轮触发了阈值则入队异步压缩（须在本轮消息已落库之后调用）。"""
    if background_tasks is None:
        return
    if not state.get("should_update_memory"):
        return
    cid = (state.get("character_id") or "").strip()
    if not cid:
        return
    uid = (state.get("anon_user_id") or "").strip() or None
    background_tasks.add_task(run_long_memory_compression_job, cid, uid)
