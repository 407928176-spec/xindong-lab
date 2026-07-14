"""角色实例与对话：阶段 5.7 起 /chat 走 LangGraph + save_and_respond；保留 mock 供本地脚本或回退。"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal, cast

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.services.attachment_service import list_attachment_ids_for_messages

from app.engine.graph import build_compiled_graph, route_after_evaluation
from app.engine.memory_compression import enqueue_long_memory_compression_after_graph
from app.engine.nodes.ending_judge import ending_judge
from app.engine.nodes.evaluate_state import compute_heartbeat_score, evaluate_state
from app.engine.no_reply import NO_REPLY_DISPLAY_TEXT, NoReplyStreamSplitter
from app.engine.nodes.generate_reply import stream_character_reply_tokens
from app.engine.nodes.load_context import load_context, user_message_count
from app.engine.nodes.memory_manager import memory_manager
from app.engine.nodes.save_and_respond import save_and_respond
from app.engine.persona_generator import generate_persona_prompt
from app.engine.multimodal_content import (
    bind_attachments_to_message,
    ensure_character_chat_attachments_ready,
)
from app.db.session import SessionLocal
from app.engine.state import ConversationState, minimal_conversation_state
from app.models.character import Character
from app.models.enums import AttachmentScene, CharacterStatus, MessageRole
from app.models.message import Message
from app.models.persona import Persona
from app.schemas.character import (
    CharacterChatRequest,
    CharacterChatResponse,
    CharacterCreatedResponse,
    CharacterDetailResponse,
    CharacterListItem,
    CharacterCreateRequest,
    CharacterMessageItem,
    EndingPayload,
)


class CharacterChatEndedError(Exception):
    """终局后禁止继续发消息；路由层映射为 HTTP 409。"""

    def __init__(self, message: str = "对话已结束，无法继续发送") -> None:
        self.message = message
        super().__init__(message)


class CharacterChatBusyError(Exception):
    """上一轮对话仍在处理中；路由层映射为 HTTP 409。"""

    def __init__(self, message: str = "上一轮对话还在处理中，请稍候") -> None:
        self.message = message
        super().__init__(message)


# 每个 character_id 一把锁，保证同一角色的对话请求串行执行，消除并发竞态。
_character_chat_locks_guard: threading.Lock = threading.Lock()
_character_chat_locks: dict[str, threading.Lock] = {}


def _acquire_character_chat_lock(character_id: str) -> threading.Lock:
    """非阻塞地获取该角色的对话锁；已被占用则抛 CharacterChatBusyError。"""
    with _character_chat_locks_guard:
        lock = _character_chat_locks.setdefault(character_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise CharacterChatBusyError()
    return lock


class CharacterPersistenceError(Exception):
    """图跑完但缺少 persisted 回执时抛出；路由层映射为 500。"""

    def __init__(self, message: str = "对话落库未完成") -> None:
        self.message = message
        super().__init__(message)


def _chat_parties_or_none(db: Session, character_id: str) -> tuple[Character, Persona] | None:
    character = db.get(Character, character_id)
    if character is None:
        return None
    persona = db.get(Persona, character.persona_id)
    if persona is None:
        return None
    if character.is_ended or character.status == CharacterStatus.ENDED.value:
        raise CharacterChatEndedError()
    return character, persona


def _build_chat_response_from_merged_state(
    state: dict[str, Any],
    user_content: str,
    user_attachment_ids: list[str] | None = None,
) -> CharacterChatResponse:
    if not state.get("persisted_user_message_id") or not state.get("persisted_assistant_message_id"):
        raise CharacterPersistenceError()

    ending: EndingPayload | None = None
    er = (state.get("ending_result") or "").strip()
    if er:
        ending = EndingPayload(
            result=er,
            evaluation=(state.get("ending_evaluation") or "").strip(),
            user_review=(state.get("user_review") or "").strip() or None,
        )

    pr = int(state["persisted_round"])
    hb = int(state["persisted_heartbeat_score"])
    u_at = state["persisted_user_message_at"]
    a_at = state["persisted_assistant_message_at"]
    if not isinstance(u_at, datetime) or not isinstance(a_at, datetime):
        raise CharacterPersistenceError("persisted 时间戳类型异常")

    no_reply = bool(state.get("character_no_reply"))
    assistant_text = (state.get("character_reply") or "").strip()
    assistant_display = NO_REPLY_DISPLAY_TEXT if no_reply else assistant_text
    assistant_type: Literal["normal", "no_reply"] = "no_reply" if no_reply else "normal"

    return CharacterChatResponse(
        assistant_message=assistant_text,
        assistant_no_reply=no_reply,
        assistant_display_text=assistant_display,
        assistant_message_type=assistant_type,
        user_message=CharacterMessageItem(
            id=str(state["persisted_user_message_id"]),
            role=MessageRole.USER.value,
            content=user_content,
            round_number=pr,
            created_at=u_at,
            display_text=user_content,
            is_no_reply=False,
            message_type="normal",
            attachment_ids=list(user_attachment_ids) if user_attachment_ids else [],
        ),
        assistant_message_item=CharacterMessageItem(
            id=str(state["persisted_assistant_message_id"]),
            role=MessageRole.CHARACTER.value,
            content=assistant_text,
            round_number=pr,
            created_at=a_at,
            is_no_reply=no_reply,
            message_type=assistant_type,
            display_text=assistant_display,
        ),
        heartbeat_score=hb,
        round=pr,
        ending=ending,
    )


def _message_item(m: Message, attachment_ids: list[str] | None = None) -> CharacterMessageItem:
    ipc = m.internal_phase_change
    is_nr = (
        m.role == MessageRole.CHARACTER.value
        and isinstance(ipc, dict)
        and ipc.get("no_reply") is True
    )
    text = m.content or ""
    display = NO_REPLY_DISPLAY_TEXT if is_nr else text
    msg_type: Literal["normal", "no_reply"] = "no_reply" if is_nr else "normal"
    return CharacterMessageItem(
        id=m.id,
        role=m.role,  # type: ignore[arg-type]
        content=text,
        round_number=m.round_number,
        created_at=m.created_at,
        is_no_reply=is_nr,
        message_type=msg_type,
        display_text=display,
        attachment_ids=list(attachment_ids) if attachment_ids else [],
    )


def _message_preview(m: Message | None) -> str:
    if m is None:
        return ""
    ipc = m.internal_phase_change
    if (
        m.role == MessageRole.CHARACTER.value
        and isinstance(ipc, dict)
        and ipc.get("no_reply") is True
    ):
        preview = NO_REPLY_DISPLAY_TEXT
    else:
        preview = (m.content or "").strip().replace("\n", " ")
    return preview[:80] + "…" if len(preview) > 80 else preview


def _latest_message_for_preview(db: Session, character_id: str) -> Message | None:
    return db.scalar(
        select(Message)
        .where(Message.character_id == character_id)
        .order_by(
            Message.round_number.desc(),
            case((Message.role == MessageRole.CHARACTER.value, 1), else_=0).desc(),
            Message.created_at.desc(),
        )
        .limit(1)
    )


def _latest_message_preview(db: Session, character_id: str) -> str:
    return _message_preview(_latest_message_for_preview(db, character_id))


def _mock_assistant_reply(persona: Persona, user_text: str) -> str:
    """确定性 mock：引用人设昵称与用户原话，便于阶段 4 自检。"""
    name = (persona.display_name or "TA").strip() or "TA"
    snippet = user_text.strip().replace("\n", " ")[:120]
    return (
        f"（mock 回复）{name} 想了想，轻声回你：「{snippet}」——我这边先按你的描述演一下语气；"
        f"等阶段 5 接上真实模型后，会更像真人。"
    )


def create_character(db: Session, payload: CharacterCreateRequest, user_id: str) -> CharacterCreatedResponse:
    persona = db.get(Persona, payload.persona_id)
    if persona is None or persona.user_id != user_id:
        raise ValueError("人设不存在")

    display = (payload.display_name or "").strip() or persona.display_name.strip() or "未命名"

    # 从 persona 的 hidden_evolution_params 读取初始五维状态，用于正确设置初始心动值
    def _extract_initial_hidden_state(params: Any) -> dict[str, float]:
        keys = ("comfort", "interest", "trust", "alertness", "baseline_compatibility")
        defaults: dict[str, float] = {k: 50.0 for k in keys}
        try:
            ihs = (params or {}).get("initial_hidden_state", {})
            for k in keys:
                v = ihs.get(k)
                if isinstance(v, (int, float)):
                    defaults[k] = float(v)
        except Exception:
            pass
        return defaults

    initial_hidden = _extract_initial_hidden_state(persona.hidden_evolution_params)
    initial_heartbeat = int(round(compute_heartbeat_score(initial_hidden)))

    character_info: dict[str, Any] = {
        "persona_id": persona.id,
        "creation_method": persona.creation_method,
        "created_at": persona.created_at.isoformat(),
        "extract_snapshot": persona.extract_snapshot,
        "display_name": persona.display_name,
        "identity_summary": persona.identity_summary,
        "personality_summary": persona.personality_summary,
        "interests": persona.interests,
        "chat_style": persona.chat_style,
        "visible_background": persona.visible_background,
        "hidden_initial_tendency": persona.hidden_initial_tendency,
        "hidden_impression_baseline": persona.hidden_impression_baseline,
        "hidden_key_judgment": persona.hidden_key_judgment,
        "hidden_pacing_tolerance": persona.hidden_pacing_tolerance,
        "hidden_sensitivity_points": persona.hidden_sensitivity_points,
        "hidden_evolution_params": persona.hidden_evolution_params,
    }
    # 优先使用 Persona 上已缓存的 persona_prompt，避免重复 LLM 调用
    if persona.cached_persona_prompt:
        resolved_prompt = persona.cached_persona_prompt
    else:
        resolved_prompt = generate_persona_prompt(character_info)
        if resolved_prompt:
            persona.cached_persona_prompt = resolved_prompt
            db.flush()

    character = Character(
        persona_id=persona.id,
        user_id=user_id,
        display_name=display[:128],
        status=CharacterStatus.IN_PROGRESS.value,
        hidden_state_snapshot=initial_hidden,
        heartbeat_score=initial_heartbeat,
        persona_prompt=resolved_prompt,
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return CharacterCreatedResponse(
        id=character.id,
        persona_id=character.persona_id,
        display_name=character.display_name,
        heartbeat_score=character.heartbeat_score,
    )


def list_characters(db: Session, user_id: str) -> list[CharacterListItem]:
    stmt = (
        select(Character, Persona)
        .join(Persona, Persona.id == Character.persona_id)
        .where(
            Character.user_id == user_id,
            Character.deleted_at.is_(None),
            # ENDING_UNREAD：终局已触发但用户未查看，仍在首页显示；其余有 ending 行的归档
            or_(
                ~Character.ending.has(),
                Character.status == CharacterStatus.ENDING_UNREAD.value,
            ),
        )
    )
    rows = list(db.execute(stmt).all())

    # 置顶区按 pinned_at 倒序，非置顶区按 updated_at 倒序
    pinned_rows = sorted(
        [r for r in rows if r[0].is_pinned],
        key=lambda r: r[0].pinned_at or r[0].updated_at,
        reverse=True,
    )
    regular_rows = sorted(
        [r for r in rows if not r[0].is_pinned],
        key=lambda r: r[0].updated_at,
        reverse=True,
    )
    ordered_rows = pinned_rows + regular_rows

    out: list[CharacterListItem] = []
    for character, persona in ordered_rows:
        preview = _latest_message_preview(db, character.id)
        ending_payload: EndingPayload | None = None
        if character.ending is not None:
            ending_payload = EndingPayload(
                result=character.ending.ending_kind,
                evaluation=character.ending.content or "",
                user_review=character.ending.user_review or None,
            )
        out.append(
            CharacterListItem(
                id=character.id,
                display_name=character.display_name,
                persona_id=persona.id,
                persona_display_name=persona.display_name,
                heartbeat_score=character.heartbeat_score,
                status=character.status,
                last_message_preview=preview,
                updated_at=character.updated_at,
                is_pinned=character.is_pinned,
                ending=ending_payload,
            )
        )
    return out


def toggle_pin_character(db: Session, character_id: str, user_id: str) -> bool:
    """切换角色置顶状态，返回切换后的 is_pinned 值。"""
    character = db.get(Character, character_id)
    if character is None or character.user_id != user_id:
        raise ValueError(f"角色不存在: {character_id}")
    character.is_pinned = not character.is_pinned
    character.pinned_at = datetime.now(tz=timezone.utc) if character.is_pinned else None
    db.commit()
    return character.is_pinned


def get_character_detail(db: Session, character_id: str, user_id: str) -> CharacterDetailResponse | None:
    character = db.get(Character, character_id)
    if character is None or character.deleted_at is not None or character.user_id != user_id:
        return None
    persona = db.get(Persona, character.persona_id)
    if persona is None:
        return None

    msg_stmt = (
        select(Message)
        .where(Message.character_id == character_id)
        .order_by(Message.created_at.asc(), Message.round_number.asc())
    )
    messages = list(db.scalars(msg_stmt))
    mids = [m.id for m in messages]
    amap = list_attachment_ids_for_messages(db, mids)
    ending = None
    if character.ending is not None:
        ending = EndingPayload(
            result=character.ending.ending_kind,
            evaluation=character.ending.content or "",
            user_review=character.ending.user_review or None,
        )
    return CharacterDetailResponse(
        id=character.id,
        display_name=character.display_name,
        persona_id=persona.id,
        persona_display_name=persona.display_name,
        heartbeat_score=character.heartbeat_score,
        status=character.status,
        messages=[_message_item(m, amap.get(m.id)) for m in messages],
        ending=ending,
    )


def delete_character(db: Session, character_id: str, user_id: str) -> None:
    """软删除角色实例。"""
    from datetime import datetime, timezone

    character = db.get(Character, character_id)
    if character is None or character.user_id != user_id:
        raise ValueError("角色不存在")
    character.deleted_at = datetime.now(tz=timezone.utc)
    db.commit()


def chat_with_character(
    db: Session,
    character_id: str,
    payload: CharacterChatRequest,
    background_tasks: Any = None,
    user_id: str = "",
) -> CharacterChatResponse | None:
    """终局前校验 → LangGraph invoke → 按 persisted_* 与 result 组装响应；可选入队长记忆压缩。"""
    lock = _acquire_character_chat_lock(character_id)  # 并发第二请求直接抛 CharacterChatBusyError
    try:
        parties = _chat_parties_or_none(db, character_id)
        if parties is None:
            return None
        character_obj, _ = parties
        if character_obj.user_id != user_id:
            return None

        # 发送时立即更新 updated_at，使卡片在列表中即时排到顶端（save_and_respond 还会再更新一次）
        character_obj.updated_at = datetime.now(timezone.utc)
        db.commit()

        if payload.attachment_ids:
            ensure_character_chat_attachments_ready(
                db,
                anon_user_id=user_id,
                character_id=character_id,
                draft_turn_id=payload.draft_turn_id.strip(),
                attachment_ids=list(payload.attachment_ids),
            )

        user_content = payload.content.strip()
        base = minimal_conversation_state()
        base["character_id"] = character_id
        base["user_message"] = user_content
        base["anon_user_id"] = user_id
        base["pending_attachment_ids"] = list(payload.attachment_ids)
        base["draft_turn_id"] = (payload.draft_turn_id or "").strip()

        graph = build_compiled_graph()
        result = graph.invoke(base)
        merged = dict(result)

        if not merged.get("persisted_user_message_id") or not merged.get("persisted_assistant_message_id"):
            raise CharacterPersistenceError()

        if payload.attachment_ids:
            bind_attachments_to_message(
                db,
                anon_user_id=user_id,
                attachment_ids=list(payload.attachment_ids),
                message_id=str(merged["persisted_user_message_id"]),
                scene=AttachmentScene.CHARACTER_CHAT.value,
                conversation_id=character_id,
                character_id=character_id,
            )

        enqueue_long_memory_compression_after_graph(cast(ConversationState, merged), background_tasks)
        return _build_chat_response_from_merged_state(merged, user_content, list(payload.attachment_ids))
    finally:
        lock.release()


def _sse_line(obj: dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def iter_character_chat_sse_lines(
    character_id: str,
    payload: CharacterChatRequest,
    background_tasks: Any,
    user_id: str = "",
) -> Iterator[str]:
    """load → 流式角色回复 → evaluate → 分支 → save；SSE `data:` 行 JSON。

    DB 连接仅在 LLM 流**前**（校验/附件）和流**后**（附件绑定）各开一段短 session，
    LLM 慢速输出期间不占任何连接池连接，防止并发时连接池耗尽。
    """
    user_content = payload.content.strip()

    # 非阻塞地拿锁；同一角色并发第二请求直接返回错误，避免历史读到脏数据。
    acquired = False
    try:
        lock = _acquire_character_chat_lock(character_id)
        acquired = True
    except CharacterChatBusyError as exc:
        yield _sse_line({"type": "error", "httpStatus": 409, "detail": exc.message})
        return

    try:
        # --- 前置短 session：校验角色归属 + 附件就绪，用完立即关闭 ---
        pre_db = SessionLocal()
        try:
            try:
                parties = _chat_parties_or_none(pre_db, character_id)
            except CharacterChatEndedError as exc:
                yield _sse_line({"type": "error", "httpStatus": 409, "detail": exc.message})
                return
            if parties is None:
                yield _sse_line({"type": "error", "httpStatus": 404, "detail": "角色不存在"})
                return
            character_obj, _ = parties
            if character_obj.user_id != user_id:
                yield _sse_line({"type": "error", "httpStatus": 404, "detail": "角色不存在"})
                return

            if payload.attachment_ids:
                try:
                    ensure_character_chat_attachments_ready(
                        pre_db,
                        anon_user_id=user_id,
                        character_id=character_id,
                        draft_turn_id=payload.draft_turn_id.strip(),
                        attachment_ids=list(payload.attachment_ids),
                    )
                except ValueError as exc:
                    yield _sse_line({"type": "error", "httpStatus": 400, "detail": str(exc)})
                    return
        finally:
            pre_db.close()
        # --- 前置短 session 结束，此后 LLM 流式期间无连接占用 ---

        s: dict[str, Any] = dict(minimal_conversation_state())
        s["character_id"] = character_id
        s["user_message"] = user_content
        s["anon_user_id"] = user_id
        s["pending_attachment_ids"] = list(payload.attachment_ids)
        s["draft_turn_id"] = (payload.draft_turn_id or "").strip()
        s.update(load_context(cast(ConversationState, s)))

        splitter = NoReplyStreamSplitter()
        try:
            for chunk in stream_character_reply_tokens(cast(ConversationState, s)):
                if not chunk:
                    continue
                splitter.feed(chunk)

            splitter.finish()

            reply_text, no_reply = splitter.normalized_reply()
            s["character_reply"] = reply_text
            s["character_no_reply"] = no_reply
            yield _sse_line({
                "type": "assistant_done",
                "text": NO_REPLY_DISPLAY_TEXT if no_reply else reply_text,
                "is_no_reply": no_reply,
            })

            s.update(evaluate_state(cast(ConversationState, s)))
            nxt = route_after_evaluation(cast(ConversationState, s))
            if nxt == "ending_judge":
                yield _sse_line({"type": "ending_pending"})
                s.update(ending_judge(cast(ConversationState, s)))
            else:
                s.update(memory_manager(cast(ConversationState, s)))
            s.update(save_and_respond(cast(ConversationState, s)))

            # --- 后置短 session：附件绑定，用完立即关闭 ---
            if payload.attachment_ids:
                post_db = SessionLocal()
                try:
                    bind_attachments_to_message(
                        post_db,
                        anon_user_id=user_id,
                        attachment_ids=list(payload.attachment_ids),
                        message_id=str(s["persisted_user_message_id"]),
                        scene=AttachmentScene.CHARACTER_CHAT.value,
                        conversation_id=character_id,
                        character_id=character_id,
                    )
                finally:
                    post_db.close()

            enqueue_long_memory_compression_after_graph(cast(ConversationState, s), background_tasks)
            resp = _build_chat_response_from_merged_state(s, user_content, list(payload.attachment_ids))
            yield _sse_line({"type": "done", **json.loads(resp.model_dump_json())})
        except CharacterPersistenceError as exc:
            yield _sse_line({"type": "error", "httpStatus": 500, "detail": exc.message})
        except Exception:
            import logging

            logging.getLogger(__name__).exception("iter_character_chat_sse_lines")
            yield _sse_line({"type": "error", "httpStatus": 500, "detail": "对话处理失败"})
    finally:
        if acquired:
            lock.release()


def chat_with_character_mock(
    db: Session,
    character_id: str,
    payload: CharacterChatRequest,
) -> CharacterChatResponse | None:
    """阶段 4 风格 mock；与正式链路相同 round 语义（同轮同 round_number）。"""
    character = db.get(Character, character_id)
    if character is None:
        return None
    persona = db.get(Persona, character.persona_id)
    if persona is None:
        return None

    persisted_round = user_message_count(db, character_id) + 1
    user_msg = Message(
        character_id=character.id,
        role=MessageRole.USER.value,
        content=payload.content.strip(),
        round_number=persisted_round,
    )
    db.add(user_msg)
    db.flush()

    assistant_text = _mock_assistant_reply(persona, payload.content)
    asst_msg = Message(
        character_id=character.id,
        role=MessageRole.CHARACTER.value,
        content=assistant_text,
        round_number=persisted_round,
    )
    db.add(asst_msg)
    character.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_msg)
    db.refresh(asst_msg)
    db.refresh(character)

    return CharacterChatResponse(
        assistant_message=assistant_text,
        assistant_display_text=assistant_text,
        assistant_no_reply=False,
        assistant_message_type="normal",
        user_message=_message_item(user_msg),
        assistant_message_item=_message_item(asst_msg),
        heartbeat_score=character.heartbeat_score,
        round=persisted_round,
        ending=None,
    )


def list_archived_characters(db: Session, user_id: str) -> list[CharacterListItem]:
    """角色回收站列表：已删除的角色，按删除时间倒序。"""

    stmt = select(Character, Persona).join(Persona, Persona.id == Character.persona_id).where(Character.deleted_at.isnot(None), Character.user_id == user_id)
    rows = list(db.execute(stmt).all())
    rows.sort(key=lambda r: r[0].deleted_at or r[0].created_at, reverse=True)

    out: list[CharacterListItem] = []
    for character, persona in rows:
        preview = _latest_message_preview(db, character.id)
        ending_payload: EndingPayload | None = None
        if character.ending is not None:
            ending_payload = EndingPayload(
                result=character.ending.ending_kind,
                evaluation=character.ending.content or "",
                user_review=character.ending.user_review or None,
            )
        out.append(
            CharacterListItem(
                id=character.id,
                display_name=character.display_name,
                persona_id=persona.id,
                persona_display_name=persona.display_name,
                heartbeat_score=character.heartbeat_score,
                status=character.status,
                last_message_preview=preview,
                updated_at=character.updated_at,
                is_pinned=character.is_pinned,
                ending=ending_payload,
            )
        )
    return out


def list_ended_characters(db: Session, user_id: str) -> list[CharacterListItem]:
    """缘散录列表：已到达终局、且未被删除的角色。"""
    stmt = (
        select(Character, Persona)
        .join(Persona, Persona.id == Character.persona_id)
        .where(
            Character.user_id == user_id,
            Character.deleted_at.is_(None),
            Character.ending.has(),
            # ENDING_UNREAD 仍在首页展示，只有已确认（ENDED 或旧数据其他状态）才进入缘散录
            Character.status != CharacterStatus.ENDING_UNREAD.value,
        )
    )
    rows = list(db.execute(stmt).all())
    rows.sort(key=lambda r: r[0].updated_at, reverse=True)

    out: list[CharacterListItem] = []
    for character, persona in rows:
        preview = _latest_message_preview(db, character.id)
        ending_payload: EndingPayload | None = None
        if character.ending is not None:
            ending_payload = EndingPayload(
                result=character.ending.ending_kind,
                evaluation=character.ending.content or "",
                user_review=character.ending.user_review or None,
            )
        out.append(
            CharacterListItem(
                id=character.id,
                display_name=character.display_name,
                persona_id=persona.id,
                persona_display_name=persona.display_name,
                heartbeat_score=character.heartbeat_score,
                status=character.status,
                last_message_preview=preview,
                updated_at=character.updated_at,
                is_pinned=character.is_pinned,
                ending=ending_payload,
            )
        )
    return out


def restore_character(db: Session, character_id: str, user_id: str) -> None:
    """恢复已删除角色。"""
    character = db.get(Character, character_id)
    if character is None or character.user_id != user_id:
        raise ValueError("角色不存在")
    if character.deleted_at is None:
        raise ValueError("角色未被删除")
    character.deleted_at = None
    db.commit()


def permanently_delete_character(db: Session, character_id: str, user_id: str) -> None:
    """永久删除角色及其所有相关数据（消息、复盘、终局等）。"""
    character = db.get(Character, character_id)
    if character is None or character.user_id != user_id:
        raise ValueError("角色不存在")

    # ORM 级联关系会自动删除子表数据
    db.delete(character)
    db.commit()


def clear_archived_characters(db: Session, user_id: str) -> int:
    """清空角色回收站：物理删除所有已软删除的角色（及其级联子表）。返回删除数量。"""
    archived = list(db.scalars(select(Character).where(Character.deleted_at.isnot(None), Character.user_id == user_id)))
    if not archived:
        return 0
    for character in archived:
        db.delete(character)
    db.commit()
    return len(archived)


def acknowledge_ending(db: Session, character_id: str, user_id: str) -> None:
    """用户查看终局后调用：将状态从 ENDING_UNREAD 改为 ENDED，使卡片从首页移入缘散录。
    幂等：已是 ENDED 或其他状态时不做任何操作。"""
    character = db.get(Character, character_id)
    if character is None or character.user_id != user_id:
        raise ValueError("角色不存在")
    if character.status == CharacterStatus.ENDING_UNREAD.value:
        character.status = CharacterStatus.ENDED.value
        db.commit()
