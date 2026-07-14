"""附件业务：上传落盘、读取、草稿配额。

原先走对象存储时是三步（预签名 → 客户端直传 → 确认）。存本地硬盘后没有直传的必要，
压缩成一步：浏览器 multipart 传给后端，后端校验完直接落盘并建记录。
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.attachment_policy import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_IMAGE_BYTES,
    MIME_TO_SUFFIX,
    MODEL_ATTACHMENT_ALLOWED_MIME_TYPES,
    MODEL_IMAGE_ALLOWED_MIME_TYPES,
)
from app.models.attachment import Attachment
from app.models.character import Character
from app.models.enums import AttachmentScene, AttachmentStatus, AttachmentStorageProvider
from app.services import local_storage_service


def _suffix_from_filename(file_name: str) -> str:
    low = file_name.strip().lower()
    if "." not in low:
        raise ValueError("文件名缺少扩展名")
    return "." + low.rsplit(".", 1)[-1]


def _validate_mime_extension(mime_type: str, file_name: str) -> str:
    """MIME 与扩展名双向校验：两者都要在白名单里，且必须互相匹配。"""
    mt = mime_type.strip().lower()
    if mt not in MODEL_ATTACHMENT_ALLOWED_MIME_TYPES:
        raise ValueError("不支持的文件类型")
    suf = _suffix_from_filename(file_name)
    allowed_suffixes = MIME_TO_SUFFIX.get(mt)
    if not allowed_suffixes or suf not in allowed_suffixes:
        raise ValueError("文件扩展名与类型不匹配")
    return suf


def _validate_size(size: int, mime_type: str) -> None:
    if size <= 0:
        raise ValueError("文件为空")
    # 图片会被 base64 内联进模型请求（体积膨胀约 1/3），所以上限比普通文件更严。
    if mime_type in MODEL_IMAGE_ALLOWED_MIME_TYPES:
        if size > MAX_IMAGE_BYTES:
            raise ValueError(f"图片不能超过 {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        return
    if size > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"文件不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB")


def _count_draft_attachments(
    db: Session,
    *,
    user_id: str,
    scene: str,
    conversation_id: str,
    draft_turn_id: str,
) -> int:
    stmt = (
        select(func.count())
        .select_from(Attachment)
        .where(
            Attachment.user_id == user_id,
            Attachment.scene == scene,
            Attachment.conversation_id == conversation_id,
            Attachment.draft_turn_id == draft_turn_id,
            Attachment.message_id.is_(None),
            Attachment.status.in_(
                [AttachmentStatus.PENDING.value, AttachmentStatus.UPLOADED.value],
            ),
        )
    )
    return int(db.scalar(stmt) or 0)


def upload_attachment(
    db: Session,
    *,
    user_id: str,
    file_name: str,
    mime_type: str,
    data: bytes,
    scene: str,
    conversation_id: str,
    draft_turn_id: str,
) -> Attachment:
    """校验 → 落盘 → 建记录。一步完成，返回已是 UPLOADED 状态的附件行。"""
    _validate_size(len(data), mime_type.strip().lower())
    suf = _validate_mime_extension(mime_type, file_name)

    try:
        uuid.UUID(draft_turn_id)
        uuid.UUID(conversation_id)
        uuid.UUID(user_id)
    except ValueError as exc:
        raise ValueError("conversation_id / draft_turn_id / user 必须为 UUID") from exc

    sc = scene.strip()
    if sc not in (AttachmentScene.PERSONA_CREATION.value, AttachmentScene.CHARACTER_CHAT.value):
        raise ValueError("非法 scene")

    if sc == AttachmentScene.CHARACTER_CHAT.value:
        char = db.get(Character, conversation_id)
        if char is None:
            raise ValueError("角色不存在")
        character_id = conversation_id
    else:
        character_id = None

    if (
        _count_draft_attachments(
            db,
            user_id=user_id,
            scene=sc,
            conversation_id=conversation_id,
            draft_turn_id=draft_turn_id,
        )
        >= MAX_ATTACHMENTS_PER_MESSAGE
    ):
        raise ValueError(f"单轮附件不能超过 {MAX_ATTACHMENTS_PER_MESSAGE} 个")

    object_key = local_storage_service.generate_object_key(
        scene=sc,
        conversation_id=conversation_id,
        draft_turn_id=draft_turn_id,
        file_suffix=suf,
    )
    size = local_storage_service.save_bytes(object_key, data)

    att = Attachment(
        user_id=user_id,
        scene=sc,
        conversation_id=conversation_id,
        character_id=character_id,
        draft_turn_id=draft_turn_id,
        file_name=file_name.strip()[:512],
        mime_type=mime_type.strip().lower(),
        file_ext=suf,
        size=size,
        object_key=object_key,
        storage_provider=AttachmentStorageProvider.LOCAL.value,
        # 文件已经在硬盘上了，没有「等待客户端直传」这个中间态。
        status=AttachmentStatus.UPLOADED.value,
    )
    try:
        db.add(att)
        db.commit()
        db.refresh(att)
    except Exception:
        # 建记录失败就把已落盘的文件删掉，避免留下没人认领的孤儿文件。
        local_storage_service.delete(object_key)
        raise
    return att


def get_attachment_for_user(db: Session, *, user_id: str, attachment_id: str) -> Attachment:
    """取附件行并校验归属与就绪状态。只要元信息时用这个，不必读盘。"""
    row = db.get(Attachment, attachment_id)
    if row is None:
        raise ValueError("附件不存在")
    if row.user_id != user_id:
        raise PermissionError("无权访问该附件")
    if row.status != AttachmentStatus.UPLOADED.value:
        raise ValueError("附件未就绪")
    return row


def read_attachment_bytes(db: Session, *, user_id: str, attachment_id: str) -> tuple[Attachment, bytes]:
    """读取附件内容，同时校验归属。"""
    row = get_attachment_for_user(db, user_id=user_id, attachment_id=attachment_id)
    local_storage_service.validate_object_key_strict(
        row.object_key,
        scene=row.scene,
        conversation_id=row.conversation_id,
    )
    return row, local_storage_service.read_bytes(row.object_key)


def list_uploaded_persona_conversation_attachments(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
) -> list[Attachment]:
    """人设创建会话下全部已上传附件（confirm_generate 聚合）；按 created_at、draft_turn_id 排序。"""
    stmt = (
        select(Attachment)
        .where(
            Attachment.user_id == user_id,
            Attachment.scene == AttachmentScene.PERSONA_CREATION.value,
            Attachment.conversation_id == conversation_id,
            Attachment.status == AttachmentStatus.UPLOADED.value,
        )
        .order_by(Attachment.created_at.asc(), Attachment.draft_turn_id.asc())
    )
    return list(db.scalars(stmt))


def list_attachment_ids_for_messages(db: Session, message_ids: list[str]) -> dict[str, list[str]]:
    """message_id -> attachment_id 列表。"""
    if not message_ids:
        return {}
    stmt = select(Attachment).where(Attachment.message_id.in_(message_ids))
    rows = list(db.scalars(stmt))
    m: dict[str, list[str]] = {}
    for r in rows:
        mid = r.message_id
        if mid:
            m.setdefault(mid, []).append(r.id)
    return m
