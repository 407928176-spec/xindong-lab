"""人设创建相关服务。

- ``handle_persona_chat``：助手自然语言由 ``character_creation_chat_prompt.md`` + ``call_llm``；
  右侧结构化预览在聊天阶段仍为 ``build_mock_persona_extract``；确认生成后以 ``confirm_generate_persona`` 真快照为准。
- ``confirm_generate_persona``：静默抽取 ``character_creation_extract_prompt``。

人设创建对话与静默抽取都使用辅助模型（见 ``llm_client.get_auxiliary_model``）。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.engine.attachment_processing import (
    assemble_user_llm_content_list,
    process_attachment_ids_for_llm,
    transcript_attachment_round_notes,
)
from app.engine.llm_client import call_llm, get_auxiliary_model, get_extract_model
from app.engine.multimodal_content import ensure_persona_attachment_rows_ready
from app.engine.persona_extract_validator import validate_and_normalize_persona_extract
from app.engine.prompts.loader import read_prompt
from app.models.enums import AttachmentScene, PersonaCreationMethod
from app.models.persona import Persona
from app.schemas.persona import (
    ChatMessage,
    PersonaChatRequest,
    PersonaChatResponse,
    PersonaConfirmGenerateRequest,
    PersonaConfirmGenerateResponse,
    PersonaCreatedResponse,
    PersonaDetailResponse,
    PersonaListItem,
    PersonaSaveRequest,
)
from app.schemas.persona_extract_v06 import PersonaExtractV06, VisibleLayerV06, default_persona_extract_v06
from app.services.attachment_service import list_uploaded_persona_conversation_attachments
from app.services.persona_extract_mapping import extract_to_persona_flat_fields

logger = logging.getLogger(__name__)


def _user_texts(messages: list[ChatMessage]) -> list[str]:
    return [m.content.strip() for m in messages if m.role == "user" and m.content.strip()]


def _combined_user_text(user_texts: list[str]) -> str:
    return "\n".join(user_texts)


def _messages_to_extract_transcript(messages: list[ChatMessage]) -> str:
    """将人设创建对话转为静默抽取用纯文本（顺序与数组一致）。"""
    lines: list[str] = []
    for m in messages:
        prefix = "用户：" if m.role == "user" else "人设助手："
        lines.append(f"{prefix}{m.content.strip()}")
    return "\n".join(lines)


def _guess_display_name(text: str) -> str:
    """从用户描述里尝试抽取称呼；失败则返回空串，由上层补默认。"""
    patterns = [
        r"叫她(.{1,12})",
        r"称呼(?:她|他)?(?:叫)?[“\"](.{1,12})[”\"]",
        r"昵称(?:是|叫)?[“\"](.{1,12})[”\"]",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            name = m.group(1).strip()
            if name:
                return name[:128]
    return ""


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _hidden_from_text(text: str) -> tuple[str, str, str, str, str, dict]:
    """根据用户文本生成隐藏层 mock（与旧逻辑一致）。"""
    tendency = "中性"
    if _contains_any(text, ("冷淡", "慢热", "距离感", "不太主动")):
        tendency = "偏冷、起点更谨慎"
    if _contains_any(text, ("好感", "喜欢", "对我不错", "主动", "热情")):
        tendency = "偏暖、起点更友好"

    impression = "普通起点"
    if _contains_any(text, ("陌生", "刚认识", "不熟")):
        impression = "初识阶段：印象还在建立中"
    if _contains_any(text, ("暧昧", "拉扯", "忽冷忽热")):
        impression = "关系信号混杂：需要更多互动来稳定判断"

    judgment = "观察期：她会更在意你的表达是否自然、是否有压迫感"
    pacing = "中等：过快的推进会让她警觉，但过度退缩也会降温"
    sensitivity = "对“被审视/被测试/被套路”的表达更敏感（mock 默认值）"

    if _contains_any(text, ("追问", "查岗", "测试", "套路")):
        sensitivity = "对“被测试、被审问”的表达更敏感"

    evolution = {
        "version": 1,
        "source": "mock_stage3",
        "notes": "阶段 3 仅占位：后续由规则引擎与对话链路写入更结构化的演化参数。",
    }

    return tendency, impression, judgment, pacing, sensitivity, evolution


def _persona_chat_sse_line(obj: dict[str, object]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _get_model_generated_names(db: Session, limit: int = 80, max_chars: int = 300) -> list[str]:
    """查询最近 limit 条模型自主生成的名字，按创建时间倒序（最新在前）。

    从最新的名字开始累加字符数，超过 max_chars 时截断，确保最旧的名字被丢弃。
    顿号分隔符计入字符统计。
    """
    stmt = (
        select(Persona.display_name)
        .where(Persona.name_user_specified == False)  # noqa: E712
        .where(Persona.display_name != "未命名")
        .where(Persona.display_name != "")
        .order_by(Persona.created_at.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt))
    seen: set[str] = set()
    result: list[str] = []
    total_chars = 0
    for name in rows:
        if not name or name in seen:
            continue
        seen.add(name)
        cost = len(name) + (1 if result else 0)
        if total_chars + cost > max_chars:
            break
        result.append(name)
        total_chars += cost
    return result


_NAME_RETRY_SYSTEM = (
    "你是名字生成器。为一个虚构角色生成一个自然的中文姓名，不超过4个汉字。"
    "禁止使用以下已存在的名字：{excluded}。"
    "只输出名字本身，不要输出任何解释或标点。"
)


def _generate_replacement_name(excluded_names: list[str]) -> str:
    """名字冲突时，单次 LLM 调用生成一个不在排除列表中的替换名字。

    失败或重试后仍冲突则返回空串，由调用方决定降级策略。
    """
    excluded_str = "、".join(excluded_names) if excluded_names else "无"
    system = _NAME_RETRY_SYSTEM.format(excluded=excluded_str)
    try:
        raw = call_llm(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请生成一个名字。"},
            ],
            temperature=0.95,
            stream=False,
            model=get_auxiliary_model(),
            use_auxiliary_credentials=True,
        )
    except Exception:
        logger.warning("名字重试 LLM 调用失败", exc_info=True)
        return ""
    name = (raw or "").strip().strip('"""\'\'。，').strip()
    return name[:128] if name and name not in excluded_names else ""


def validate_persona_chat_request(payload: PersonaChatRequest) -> None:
    """人设创建对话前置校验（SSE 错误帧）；主体规则见 ``PersonaChatRequest`` 模型。"""
    if not payload.messages:
        raise ValueError("messages 不能为空")
    if payload.messages[-1].role != "user":
        raise ValueError("最后一条消息必须是 user，表示用户刚发送的内容")


def build_persona_chat_llm_messages(payload: PersonaChatRequest, user_id: str | None) -> list[dict[str, Any]]:
    """组装人设创建 Chat Completions messages（最后一轮可含多模态）。"""
    system = read_prompt("character_creation_chat_prompt.md")
    if not system:
        raise RuntimeError("无法读取 character_creation_chat_prompt.md")

    historical = payload.messages[:-1]
    last = payload.messages[-1]

    db = SessionLocal()
    try:
        # 查询去重池，填充 prompt 中的 {excluded_names} 占位符
        excluded_names = _get_model_generated_names(db)
        excluded_str = "、".join(excluded_names) if excluded_names else "（无）"
        system = system.replace("{excluded_names}", excluded_str)

        llm_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in historical:
            llm_messages.append({"role": m.role, "content": m.content.strip()})

        if payload.attachment_ids:
            if not user_id:
                raise ValueError("发送附件需要登录账号")
            ensure_persona_attachment_rows_ready(
                db,
                anon_user_id=user_id,
                conversation_id=payload.conversation_id.strip(),
                attachment_ids=list(payload.attachment_ids),
                draft_turn_id=payload.draft_turn_id.strip(),
            )
            outcome = process_attachment_ids_for_llm(
                db,
                list(payload.attachment_ids),
                anon_user_id=user_id,
                scene=AttachmentScene.PERSONA_CREATION.value,
                conversation_id=payload.conversation_id.strip(),
                character_id=None,
            )
            tail_content = assemble_user_llm_content_list(last.content.strip(), outcome)
            llm_messages.append({"role": "user", "content": tail_content})
        else:
            llm_messages.append({"role": "user", "content": last.content.strip()})
    finally:
        db.close()

    return llm_messages


def build_mock_persona_extract(user_texts: list[str]) -> PersonaExtractV06:
    """mock：根据用户已输入内容构造 persona_extract_v0.6（启发式）。"""
    text = _combined_user_text(user_texts)
    ex = default_persona_extract_v06()
    vl = ex.visible_layer

    display_name = _guess_display_name(text)
    vl.display_name = (display_name or "未命名")[:128]

    if _contains_any(text, ("学生", "上班", "工作", "程序员", "老师", "医生")):
        vl.basic_info.identity_role = vl.basic_info.identity_role or "用户提到了学习或工作相关信息（mock）"
    if _contains_any(text, ("同城", "异地", "同学", "同事", "朋友介绍", "网上认识")):
        vl.relationship_with_user.known_context = "已记录认识场景相关线索（mock）"

    personality_parts: list[str] = []
    if _contains_any(text, ("文静", "内向", "慢热", "敏感", "外向", "活泼", "理性")):
        personality_parts.append("性格关键词已从你的描述中提取（mock）。")
    if _contains_any(text, ("边界", "尊重", "不喜欢")):
        personality_parts.append("你对边界与相处方式的偏好会被纳入性格侧写（mock）。")
    if personality_parts:
        vl.explicit_personality_notes = personality_parts
    else:
        vl.explicit_personality_notes = ["性格侧写：信息还偏少，我再问你 1-2 个小问题会更像真人。"]

    if _contains_any(text, ("电影", "音乐", "游戏", "旅行", "摄影", "读书", "健身")):
        vl.explicit_interests = ["兴趣方向：已从你的描述里抓到一些线索（mock）。"]
    else:
        vl.explicit_interests = ["兴趣点：还不清楚她平时喜欢做什么。"]

    if _contains_any(text, ("回复", "聊天", "冷场", "尬", "幽默", "直球", "含蓄")):
        vl.observable_chat_style.expression_features = [
            "聊天风格：我会按你描述的沟通习惯来拟合她的回复方式（mock）。"
        ]
    else:
        vl.observable_chat_style.expression_features = [
            "聊天风格：需要你补充她平时怎么回消息、偏冷还是偏热情。"
        ]

    if _contains_any(text, ("同城", "异地", "同学", "同事", "朋友介绍", "网上认识")):
        vl.visible_background = "可见背景：已记录你们认识场景的相关线索（mock）。"
    else:
        vl.visible_background = "可见背景：你们怎么认识的、现在常见面吗？（mock 追问方向）"

    tendency, impression, judgment, pacing, sensitivity, evolution = _hidden_from_text(text)
    hid = ex.hidden_layer
    hid.initial_relation_state.initial_relation_tendency = tendency
    hid.initial_relation_state.initial_impression_baseline = impression
    hid.inferred_core_profile.summary = judgment
    hid.interaction_preferences.sensitive_topics = [sensitivity]
    hid.distinctive_hidden_notes = [
        f"节奏参考（mock）：{pacing}",
        f"演化占位（mock）：{evolution['notes']}",
    ]

    return ex


def handle_persona_chat(payload: PersonaChatRequest, user_id: str | None = None) -> PersonaChatResponse:
    """处理一轮人设创建对话：助手正文走 LLM（非流式）；extract 仍为启发式 mock。

    前端人设创建页优先使用 ``iter_persona_chat_sse_lines``（``POST /personas/chat/stream``）。
    """
    validate_persona_chat_request(payload)

    try:
        llm_messages = build_persona_chat_llm_messages(payload, user_id)
    except ValueError:
        raise
    except RuntimeError:
        raise

    try:
        assistant_raw = call_llm(
            llm_messages,
            temperature=0.8,
            stream=False,
            model=get_auxiliary_model(),
            use_auxiliary_credentials=True,
            use_web_search=True,
        )
    except ValueError:
        raise
    except Exception:
        logger.exception("人设创建对话模型调用失败")
        raise RuntimeError("人设创建对话模型调用失败，请稍后重试") from None

    assistant_stripped = assistant_raw.strip()
    if not assistant_stripped:
        raise RuntimeError("人设创建对话模型返回为空")

    user_texts = _user_texts(payload.messages)
    extract = build_mock_persona_extract(user_texts)
    return PersonaChatResponse(assistant_message=assistant_stripped, extract=extract)


def iter_persona_chat_sse_lines(
    payload: PersonaChatRequest,
    user_id: str | None = None,
) -> Iterator[str]:
    """人设创建对话：流式输出助手 token，最后一条 ``type:done`` 与 ``PersonaChatResponse`` JSON 对齐。"""
    try:
        validate_persona_chat_request(payload)
    except ValueError as exc:
        yield _persona_chat_sse_line({"type": "error", "httpStatus": 400, "detail": str(exc)})
        return

    try:
        llm_messages = build_persona_chat_llm_messages(payload, user_id)
    except ValueError as exc:
        yield _persona_chat_sse_line({"type": "error", "httpStatus": 400, "detail": str(exc)})
        return
    except RuntimeError as exc:
        yield _persona_chat_sse_line({"type": "error", "httpStatus": 502, "detail": str(exc)})
        return

    assistant_full = ""
    try:
        raw = call_llm(
            llm_messages,
            temperature=0.8,
            stream=True,
            model=get_auxiliary_model(),
            use_auxiliary_credentials=True,
            use_web_search=True,
        )
        if isinstance(raw, str):
            assistant_full = raw.strip()
            if assistant_full:
                yield _persona_chat_sse_line({"type": "token", "text": assistant_full})
        else:
            parts: list[str] = []
            for chunk in raw:
                if not chunk:
                    continue
                parts.append(chunk)
                yield _persona_chat_sse_line({"type": "token", "text": chunk})
            assistant_full = "".join(parts).strip()
    except ValueError as exc:
        yield _persona_chat_sse_line({"type": "error", "httpStatus": 400, "detail": str(exc)})
        return
    except Exception:
        logger.exception("人设创建对话流式调用失败")
        yield _persona_chat_sse_line(
            {"type": "error", "httpStatus": 502, "detail": "人设创建对话模型调用失败，请稍后重试"}
        )
        return

    if not assistant_full:
        yield _persona_chat_sse_line(
            {"type": "error", "httpStatus": 502, "detail": "人设创建对话模型返回为空"}
        )
        return

    user_texts = _user_texts(payload.messages)
    extract = build_mock_persona_extract(user_texts)
    resp = PersonaChatResponse(assistant_message=assistant_full, extract=extract)
    yield _persona_chat_sse_line({"type": "done", **json.loads(resp.model_dump_json())})


def _visible_layer_has_content(extract: PersonaExtractV06) -> bool:
    """保存前：可见层是否至少有一处实质内容。"""
    vl = extract.visible_layer
    if vl.display_name and vl.display_name.strip() and vl.display_name.strip() != "未命名":
        return True
    bi = vl.basic_info.model_dump()
    if any(v for v in bi.values() if v):
        return True
    ru = vl.relationship_with_user.model_dump()
    if any(v for v in ru.values() if v):
        return True
    if vl.explicit_personality_notes:
        return True
    if vl.explicit_interests:
        return True
    likes = vl.explicit_preferences.likes
    dislikes = vl.explicit_preferences.dislikes
    if likes or dislikes:
        return True
    obs = vl.observable_chat_style
    if obs.message_length or obs.emoji_usage or obs.initiative_pattern:
        return True
    if obs.expression_features or obs.typical_phrases:
        return True
    if vl.visible_background and vl.visible_background.strip():
        return True
    return False


def _persist_persona(
    db: Session,
    messages: list[ChatMessage],
    extract: PersonaExtractV06,
    user_id: str | None = None,
) -> Persona:
    """由已校验的 ``PersonaExtractV06`` 写入数据库（uuid 由 ORM 生成）。"""
    combined = _combined_user_text(_user_texts(messages))
    flat = extract_to_persona_flat_fields(extract)
    snapshot = flat.pop("extract_snapshot")
    assert isinstance(snapshot, dict)

    persona = Persona(
        user_id=user_id,
        creation_method=PersonaCreationMethod.TEXT_DESCRIPTION.value,
        identity_summary=flat["identity_summary"],  # type: ignore[arg-type]
        personality_summary=flat["personality_summary"],  # type: ignore[arg-type]
        interests=flat["interests"],  # type: ignore[arg-type]
        chat_style=flat["chat_style"],  # type: ignore[arg-type]
        visible_background=flat["visible_background"],  # type: ignore[arg-type]
        hidden_initial_tendency=flat["hidden_initial_tendency"],  # type: ignore[arg-type]
        hidden_impression_baseline=flat["hidden_impression_baseline"],  # type: ignore[arg-type]
        hidden_key_judgment=flat["hidden_key_judgment"],  # type: ignore[arg-type]
        hidden_pacing_tolerance=flat["hidden_pacing_tolerance"],  # type: ignore[arg-type]
        hidden_sensitivity_points=flat["hidden_sensitivity_points"],  # type: ignore[arg-type]
        hidden_evolution_params=flat["hidden_evolution_params"],  # type: ignore[arg-type]
        raw_source_material=combined[:20000],
        extract_snapshot=snapshot,
        display_name=str(flat["display_name"])[:128],
        name_user_specified=bool(extract.visible_layer.name_user_specified),
    )

    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona


def confirm_generate_persona(
    db: Session,
    payload: PersonaConfirmGenerateRequest,
    *,
    user_id: str,
) -> PersonaConfirmGenerateResponse:
    """静默抽取：transcript + 会话附件（多模态）→ JSON → 校验入库。"""
    rows = list_uploaded_persona_conversation_attachments(
        db,
        user_id=user_id,
        conversation_id=payload.conversation_id.strip(),
    )
    user_lines = _user_texts(payload.messages)
    if not user_lines and not rows:
        raise ValueError("至少需要一条非空用户消息或本会话内已上传附件")

    system = read_prompt("character_creation_extract_prompt.md")
    if not system:
        raise RuntimeError("无法读取 character_creation_extract_prompt.md")

    transcript = _messages_to_extract_transcript(payload.messages)
    draft_rank: dict[str, int] = {}
    for r in rows:
        dt = (r.draft_turn_id or "").strip()
        if dt not in draft_rank:
            draft_rank[dt] = len(draft_rank)

    notes = transcript_attachment_round_notes(rows, draft_turn_rank=draft_rank)

    header = (
        "以下为「用户与人设创建助手」的多轮对话记录（按时间顺序）。请据此输出 persona_extract JSON。\n\n"
    )
    full_text_intro = header + transcript
    if notes:
        full_text_intro += "\n\n【附件索引】\n" + "\n".join(notes)

    attachment_ids_ordered = [r.id for r in rows]

    if attachment_ids_ordered:
        outcome = process_attachment_ids_for_llm(
            db,
            attachment_ids_ordered,
            anon_user_id=anon_user_id,
            scene=AttachmentScene.PERSONA_CREATION.value,
            conversation_id=payload.conversation_id.strip(),
            character_id=None,
        )
        user_payload: str | list[dict[str, Any]] = assemble_user_llm_content_list(full_text_intro, outcome)
    else:
        user_payload = full_text_intro

    try:
        raw = call_llm(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.25,
            stream=False,
            model=get_extract_model(),
            use_auxiliary_credentials=True,
        )
    except ValueError:
        raise
    except Exception:
        logger.exception("静默抽取模型调用失败")
        raise RuntimeError("静默抽取模型调用失败，请稍后重试") from None

    normalized = validate_and_normalize_persona_extract(raw)
    try:
        extract = PersonaExtractV06.model_validate(normalized)
    except ValidationError as exc:
        raise ValueError(f"抽取结构校验失败: {exc}") from exc

    if not _visible_layer_has_content(extract):
        raise ValueError("抽取结果的可见层为空或不足以入库，请补充对话后再试")

    # 名字去重：仅对模型自主生成的名字生效
    proposed_name = (extract.visible_layer.display_name or "").strip()
    if proposed_name and proposed_name != "未命名" and not extract.visible_layer.name_user_specified:
        existing_names = _get_model_generated_names(db)
        if proposed_name in existing_names:
            logger.info("名字去重触发：%s 已存在，执行一次轻量重试", proposed_name)
            new_name = _generate_replacement_name(existing_names)
            if new_name:
                logger.info("名字已替换为：%s", new_name)
                extract.visible_layer.display_name = new_name
            else:
                logger.warning("名字重试失败，降级为未命名")
                extract.visible_layer.display_name = "未命名"

    persona = _persist_persona(db, payload.messages, extract, user_id=user_id)
    return PersonaConfirmGenerateResponse(id=persona.id, extract=extract)


def save_persona(db: Session, payload: PersonaSaveRequest, user_id: str | None = None) -> PersonaCreatedResponse:
    """将对话结果写入数据库；扁平列由 persona_extract_mapping 从抽取对象派生。

    入库前可对抽取 dict 调用 ``validate_and_normalize_persona_extract``（若来源为 LLM 原始输出）。
    """
    if not payload.messages:
        raise ValueError("messages 不能为空，用于保存原始创建依据")

    combined = _combined_user_text(_user_texts(payload.messages))
    if not combined.strip():
        raise ValueError("用户消息为空，无法保存人设")

    if not _visible_layer_has_content(payload.extract):
        raise ValueError("可见层内容为空，请先完成对话生成预览")

    persona = _persist_persona(db, payload.messages, payload.extract, user_id=user_id)
    return PersonaCreatedResponse(id=persona.id)


def list_personas(db: Session, user_id: str) -> list[PersonaListItem]:
    """人设库列表：置顶区按 pinned_at 倒序，非置顶区按创建时间倒序（仅未删除的人设）。"""
    from sqlalchemy import func
    from app.models.character import Character

    rows = list(db.scalars(select(Persona).where(Persona.deleted_at.is_(None), Persona.user_id == user_id)))
    pinned = sorted([p for p in rows if p.is_pinned], key=lambda p: p.pinned_at or p.created_at, reverse=True)
    regular = sorted([p for p in rows if not p.is_pinned], key=lambda p: p.created_at, reverse=True)

    # 一次查询统计每个人设下未删除的活跃角色数量
    counts_result = db.execute(
        select(Character.persona_id, func.count().label("cnt"))
        .where(Character.deleted_at.is_(None))
        .group_by(Character.persona_id)
    ).all()
    char_counts: dict[str, int] = {row.persona_id: row.cnt for row in counts_result}

    return [
        PersonaListItem(
            id=p.id,
            display_name=p.display_name,
            identity_summary=p.identity_summary,
            created_at=p.created_at,
            is_pinned=p.is_pinned,
            active_character_count=char_counts.get(p.id, 0),
        )
        for p in pinned + regular
    ]


def toggle_pin_persona(db: Session, persona_id: str, user_id: str) -> bool:
    """切换人设置顶状态，返回切换后的 is_pinned 值。"""
    persona = db.get(Persona, persona_id)
    if persona is None or persona.user_id != user_id:
        raise ValueError(f"人设不存在: {persona_id}")
    persona.is_pinned = not persona.is_pinned
    persona.pinned_at = datetime.now(tz=timezone.utc) if persona.is_pinned else None
    db.commit()
    return persona.is_pinned


def get_persona_characters_summary(db: Session, persona_id: str, user_id: str) -> dict:
    """返回该人设下三组角色的预览信息，用于前端删除确认弹窗和详情页展示。

    三组定义与 list_characters / list_ended_characters / list_archived_characters 口径保持一致：
    - active_in_progress：首页可见（deleted_at IS NULL 且无 ending 或 status=ENDING_UNREAD），会阻挡删除。
    - ended_characters：缘散录（deleted_at IS NULL 且有 ending 且 status≠ENDING_UNREAD），删人设时自动软删。
    - archived_characters：回收站（deleted_at IS NOT NULL），删人设时物理清除。
    """
    from sqlalchemy import and_, or_
    from app.models.character import Character
    from app.models.enums import CharacterStatus
    from app.schemas.persona import PersonaDeletePreviewItem, PersonaDeletePreviewResponse

    persona = db.get(Persona, persona_id)
    if persona is None or persona.user_id != user_id:
        raise ValueError(f"人设不存在: {persona_id}")

    def _to_item(char: Character) -> PersonaDeletePreviewItem:
        ending_kind = char.ending.ending_kind if char.ending is not None else None
        return PersonaDeletePreviewItem(
            id=char.id,
            display_name=char.display_name,
            updated_at=char.updated_at,
            ending_kind=ending_kind,
        )

    # 首页可见（阻挡删除）
    active_rows = db.query(Character).filter(
        and_(
            Character.persona_id == persona_id,
            Character.deleted_at.is_(None),
            or_(
                ~Character.ending.has(),
                Character.status == CharacterStatus.ENDING_UNREAD.value,
            ),
        )
    ).all()

    # 缘散录（已结局，未删除）
    ended_rows = db.query(Character).filter(
        and_(
            Character.persona_id == persona_id,
            Character.deleted_at.is_(None),
            Character.ending.has(),
            Character.status != CharacterStatus.ENDING_UNREAD.value,
        )
    ).all()

    # 回收站（已软删）
    archived_rows = db.query(Character).filter(
        and_(
            Character.persona_id == persona_id,
            Character.deleted_at.isnot(None),
        )
    ).all()

    return PersonaDeletePreviewResponse(
        active_in_progress=[_to_item(c) for c in active_rows],
        ended_characters=[_to_item(c) for c in ended_rows],
        archived_characters=[_to_item(c) for c in archived_rows],
    )


def delete_persona(db: Session, persona_id: str, user_id: str) -> None:
    """软删除人设：先检查首页可见角色，有则阻挡；把已结局角色软删入回收站后物理清除回收站。"""
    from sqlalchemy import and_, or_
    from app.models.character import Character
    from app.models.enums import CharacterStatus

    persona = db.get(Persona, persona_id)
    if persona is None or persona.user_id != user_id:
        raise ValueError("人设不存在")

    # 只有"首页仍可见"的角色（进行中 / ENDING_UNREAD）才阻挡删除
    active_count = db.query(Character).filter(
        and_(
            Character.persona_id == persona_id,
            Character.deleted_at.is_(None),
            or_(
                ~Character.ending.has(),
                Character.status == CharacterStatus.ENDING_UNREAD.value,
            ),
        )
    ).count()

    if active_count > 0:
        raise ValueError("无法删除：该人设下还有角色聊天未删除，请先删除对应的角色聊天")

    now = datetime.now(tz=timezone.utc)

    # 物理清除所有关联角色：已结局（缘散录）和已在回收站的统一直接删除
    to_delete = db.query(Character).filter(
        Character.persona_id == persona_id,
    ).all()
    for character in to_delete:
        db.delete(character)

    # 执行人设软删除
    persona.deleted_at = now
    db.commit()


def _visible_layer_from_flat_persona(persona: Persona) -> VisibleLayerV06:
    """extract_snapshot 缺失或校验失败时，用扁平列表拼装可读 visible_layer。"""
    base = default_persona_extract_v06()
    vl = base.visible_layer
    vl.display_name = (persona.display_name or "未命名")[:128]
    notes: list[str] = []
    if persona.identity_summary.strip():
        notes.append(persona.identity_summary.strip())
    if persona.personality_summary.strip():
        notes.append(persona.personality_summary.strip())
    vl.explicit_personality_notes = notes if notes else ["（暂无结构化快照；以下为占位摘要）"]
    interests_txt = persona.interests.strip()
    vl.explicit_interests = [interests_txt] if interests_txt else []
    vb = persona.visible_background.strip()
    vl.visible_background = vb if vb else None
    cs = persona.chat_style.strip()
    if cs:
        vl.observable_chat_style.expression_features = [f"聊天风格摘要（扁平）：{cs[:800]}"]
    return vl


def get_persona_detail(db: Session, persona_id: str, user_id: str) -> PersonaDetailResponse | None:
    """单人设详情：优先 extract_snapshot 中的 visible_layer（已删除人设返回 None）。"""
    persona = db.get(Persona, persona_id)
    if persona is None or persona.deleted_at is not None or persona.user_id != user_id:
        return None

    if persona.extract_snapshot:
        try:
            extract = PersonaExtractV06.model_validate(persona.extract_snapshot)
            vl = extract.visible_layer
        except ValidationError:
            vl = _visible_layer_from_flat_persona(persona)
    else:
        vl = _visible_layer_from_flat_persona(persona)

    return PersonaDetailResponse(
        id=persona.id,
        display_name=persona.display_name,
        created_at=persona.created_at,
        visible_layer=vl,
    )


def list_archived_personas(db: Session, user_id: str) -> list[PersonaListItem]:
    """人设回收站列表：已删除的人设，按删除时间倒序。"""
    rows = list(db.scalars(select(Persona).where(Persona.deleted_at.isnot(None), Persona.user_id == user_id)))
    rows.sort(key=lambda p: p.deleted_at or p.created_at, reverse=True)
    return [
        PersonaListItem(
            id=p.id,
            display_name=p.display_name,
            identity_summary=p.identity_summary,
            created_at=p.created_at,
            is_pinned=p.is_pinned,
        )
        for p in rows
    ]


def restore_persona(db: Session, persona_id: str, user_id: str) -> None:
    """恢复已删除人设。"""
    persona = db.get(Persona, persona_id)
    if persona is None or persona.user_id != user_id:
        raise ValueError("人设不存在")
    if persona.deleted_at is None:
        raise ValueError("人设未被删除")
    persona.deleted_at = None
    db.commit()


def permanently_delete_persona(db: Session, persona_id: str, user_id: str) -> None:
    """永久删除人设及其所有关联数据。"""
    from app.models.character import Character

    persona = db.get(Persona, persona_id)
    if persona is None or persona.user_id != user_id:
        raise ValueError("人设不存在")

    # 先永久删除所有关联角色
    characters = db.query(Character).filter(Character.persona_id == persona_id).all()
    for character in characters:
        db.delete(character)

    # 再删除人设本身
    db.delete(persona)
    db.commit()


def clear_archived_personas(db: Session, user_id: str) -> int:
    """清空人设回收站：物理删除所有已软删除的人设及其关联角色。返回删除的人设数量。"""
    from app.models.character import Character

    archived = list(db.scalars(select(Persona).where(Persona.deleted_at.isnot(None), Persona.user_id == user_id)))
    if not archived:
        return 0
    count = 0
    for persona in archived:
        characters = db.query(Character).filter(Character.persona_id == persona.id).all()
        for character in characters:
            db.delete(character)
        db.delete(persona)
        count += 1
    db.commit()
    return count
