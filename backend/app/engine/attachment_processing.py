"""将 Attachment 行转换为送入 Chat 的多模态 user content（人设 / 角色 / JSON 抽取复用）。

图片：读本地文件 → base64 data URI → image_url；TXT / DOCX：服务端解析为文本片段。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from sqlalchemy.orm import Session

from app.config.attachment_policy import (
    MAX_DOCX_PARAGRAPHS,
    MAX_EXTRACTED_TEXT_COMBINED,
    MAX_EXTRACTED_TEXT_PER_ATTACHMENT,
    MODEL_IMAGE_ALLOWED_MIME_TYPES,
)
from app.engine.multimodal_content import (
    _validate_row_for_model,
    build_image_data_uri,
    read_attachment_bytes_for_model,
)
from app.models.attachment import Attachment
from app.models.enums import AttachmentStatus

logger = logging.getLogger(__name__)

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def decode_plain_text_bytes(raw: bytes) -> tuple[str | None, str]:
    """按计划在三种解码策略中取第一份可读正文；返回 (text, strategy_note)。

    顺序：utf-8-sig strict → gb18030 strict → utf-8 replace 兜底。
    """
    if not raw:
        return None, "空文件"

    try:
        t = raw.decode("utf-8-sig", errors="strict")
        return t, "utf-8-sig"
    except UnicodeDecodeError:
        pass

    try:
        t = raw.decode("gb18030", errors="strict")
        return t, "gb18030"
    except UnicodeDecodeError:
        pass

    t = raw.decode("utf-8", errors="replace")
    return t, "utf-8-replace"


def text_readable_gate(s: str) -> bool:
    """排除空串与高度疑似乱码（不把 replace 兜底生成的噪声当晚正文喂模型）。"""
    st = (s or "").strip()
    if not st:
        return False

    n = len(st)
    repl = st.count("\ufffd")
    if repl / max(n, 1) > 0.02:
        return False

    ctrl_hits = len(_CONTROL_CHAR_RE.findall(st))
    if ctrl_hits / max(n, 1) > 0.05:
        return False

    return True


def _truncate_note_body(body: str, limit: int) -> tuple[str, bool]:
    b = body.strip()
    if len(b) <= limit:
        return b, False
    return b[:limit].rstrip() + "\n\n…【附件内容已截断】", True


def extract_docx_plain_text(data: bytes) -> str | None:
    """正文段落，最多 MAX_DOCX_PARAGRAPHS 段。"""
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("缺少 python-docx") from exc

    try:
        doc = Document(BytesIO(data))
    except Exception:
        return None

    lines: list[str] = []
    for i, p in enumerate(doc.paragraphs):
        if i >= MAX_DOCX_PARAGRAPHS:
            break
        t = (p.text or "").strip()
        if t:
            lines.append(t)
    return "\n".join(lines).strip() or None


@dataclass
class AttachmentProcessingOutcome:
    # 图片以 data: URI 形式内联进请求体（模型服务器访问不到玩家本机的文件）。
    image_data_uris: list[str] = field(default_factory=list)
    text_segments_raw: list[str] = field(default_factory=list)
    failure_summaries: list[str] = field(default_factory=list)

    def combined_text_segments_for_llm(self) -> list[str]:
        """按单附件上限截断后再做全局上限。"""
        joined_parts: list[str] = []
        budget = MAX_EXTRACTED_TEXT_COMBINED
        for seg in self.text_segments_raw:
            piece, trunc = _truncate_note_body(seg, MAX_EXTRACTED_TEXT_PER_ATTACHMENT)
            suffix = "\n…【附件内容已截断】" if trunc else ""
            chunk = piece + suffix
            if len(chunk) <= budget:
                joined_parts.append(chunk)
                budget -= len(chunk)
                if budget <= 0:
                    break
            else:
                if budget > 80:
                    joined_parts.append(chunk[:budget].rstrip() + "\n…【附件内容已截断】")
                break
        return joined_parts


def assemble_user_llm_content_list(user_text: str, outcome: AttachmentProcessingOutcome) -> list[dict[str, Any]]:
    """拼装顺序：用户正文 → 失败摘要 → 图片 → 文本附件。"""
    parts: list[dict[str, Any]] = []
    ut = (user_text or "").strip()
    if ut:
        parts.append({"type": "text", "text": ut})
    elif outcome.failure_summaries or outcome.image_data_uris or outcome.text_segments_raw:
        parts.append({"type": "text", "text": "（本条用户仅上传附件）"})

    if outcome.failure_summaries:
        parts.append({"type": "text", "text": "【部分附件未能解析】" + "；".join(outcome.failure_summaries)})

    for url in outcome.image_data_uris:
        u = (url or "").strip()
        if u.startswith("data:"):
            parts.append({"type": "image_url", "image_url": {"url": u}})

    for seg in outcome.combined_text_segments_for_llm():
        parts.append({"type": "text", "text": seg})

    if not parts:
        parts.append({"type": "text", "text": ""})
    return parts


def process_attachment_ids_for_llm(
    db: Session,
    attachment_ids: list[str],
    *,
    anon_user_id: str,
    scene: str,
    conversation_id: str,
    character_id: str | None,
) -> AttachmentProcessingOutcome:
    """按附件 id 顺序处理；解析失败记入 outcome.failure_summaries，不抛。"""
    out = AttachmentProcessingOutcome()

    for aid in attachment_ids:
        row = db.get(Attachment, aid)
        if row is None:
            out.failure_summaries.append(f"附件{aid[:8]}…不存在")
            continue
        try:
            _validate_row_for_model(
                row,
                anon_user_id=anon_user_id,
                scene=scene,
                conversation_id=conversation_id,
                character_id=character_id,
            )
        except (PermissionError, ValueError) as exc:
            out.failure_summaries.append(f"附件校验失败: {exc}")
            continue

        if row.status != AttachmentStatus.UPLOADED.value:
            out.failure_summaries.append(f"附件未就绪")
            continue

        mt = (row.mime_type or "").strip().lower()

        try:
            if mt in MODEL_IMAGE_ALLOWED_MIME_TYPES:
                raw = read_attachment_bytes_for_model(row)
                out.image_data_uris.append(build_image_data_uri(mt, raw))
            elif mt == "text/plain":
                raw = read_attachment_bytes_for_model(row)
                decoded, _how = decode_plain_text_bytes(raw)
                if decoded is None or not text_readable_gate(decoded):
                    out.failure_summaries.append(f"TXT「{row.file_name[:40]}」解码失败或不可读")
                    continue
                body, _t = _truncate_note_body(decoded, MAX_EXTRACTED_TEXT_PER_ATTACHMENT)
                label = (row.file_name or "文本").strip()[:120]
                out.text_segments_raw.append(f"【TXT:{label}】\n{body}")
            elif mt == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                raw = read_attachment_bytes_for_model(row)
                plain = extract_docx_plain_text(raw)
                if plain is None or not text_readable_gate(plain):
                    out.failure_summaries.append(f"DOCX「{row.file_name[:40]}」解析失败或不可读")
                    continue
                body, _t = _truncate_note_body(plain, MAX_EXTRACTED_TEXT_PER_ATTACHMENT)
                label = (row.file_name or "文档").strip()[:120]
                out.text_segments_raw.append(f"【DOCX:{label}】\n{body}")
            else:
                out.failure_summaries.append(f"不支持的 MIME:{mt}")
        except Exception as exc:
            logger.warning("attachment_processing failed aid=%s err=%s", aid, type(exc).__name__)
            out.failure_summaries.append(f"附件「{row.file_name[:32]}」处理失败")

    return out


def transcript_attachment_round_notes(
    rows: list[Attachment],
    *,
    draft_turn_rank: dict[str, int] | None = None,
) -> list[str]:
    """供 confirm_generate transcript：不含 URL，仅统计各轮附件类型数量。"""
    if not rows:
        return []
    by_turn: dict[str, list[Attachment]] = {}
    for r in rows:
        key = (r.draft_turn_id or "").strip() or "unknown"
        by_turn.setdefault(key, []).append(r)

    lines: list[str] = []
    rank = draft_turn_rank or {}
    ordered_turns = sorted(by_turn.keys(), key=lambda k: (rank.get(k, 10**9), k))

    for ti, turn_id in enumerate(ordered_turns, start=1):
        group = by_turn[turn_id]
        counts: dict[str, int] = {}
        for r in group:
            mt = r.mime_type or ""
            if mt in MODEL_IMAGE_ALLOWED_MIME_TYPES:
                counts["图片"] = counts.get("图片", 0) + 1
            elif mt == "text/plain":
                counts["TXT"] = counts.get("TXT", 0) + 1
            elif mt == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                counts["DOCX"] = counts.get("DOCX", 0) + 1
            else:
                counts["其它"] = counts.get("其它", 0) + 1
        parts = [f"{k}{v}个" for k, v in counts.items()]
        lines.append(f"第{ti}轮（draft_turn_id={turn_id[:8]}…）用户上传：" + "，".join(parts))
    return lines
