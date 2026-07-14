"""OpenAI 兼容 Chat 的多模态 user content 拼装。

**为什么图片要转 base64**：附件存在玩家自己的硬盘上，模型供应商的服务器不可能访问
到 ``127.0.0.1``。所以图片必须编码成 ``data:image/png;base64,...`` 内联进请求体。
这是 OpenAI 标准的 image_url 用法，各家兼容端点都支持。
"""

from __future__ import annotations

import base64
from typing import Any

from sqlalchemy.orm import Session

from app.config.attachment_policy import MODEL_ATTACHMENT_ALLOWED_MIME_TYPES
from app.models.attachment import Attachment
from app.models.enums import AttachmentScene, AttachmentStatus
from app.services import local_storage_service


def build_image_data_uri(mime_type: str, data: bytes) -> str:
    """bytes → ``data:<mime>;base64,<payload>``。"""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_openai_user_content(text: str, image_urls: list[str]) -> list[dict[str, Any]]:
    """text + image_url 组合。image_urls 接受 data: URI 或 https:// URL。"""
    parts: list[dict[str, Any]] = []
    t = (text or "").strip()
    if t:
        parts.append({"type": "text", "text": t})
    for url in image_urls:
        u = (url or "").strip()
        if not (u.startswith("data:") or u.startswith("https://")):
            raise ValueError("图片必须是 data: URI 或 HTTPS URL")
        parts.append({"type": "image_url", "image_url": {"url": u}})
    if not parts:
        parts.append({"type": "text", "text": ""})
    return parts


def _validate_row_for_model(
    row: Attachment,
    *,
    anon_user_id: str,
    scene: str,
    conversation_id: str,
    character_id: str | None,
) -> None:
    if row.user_id != anon_user_id:
        raise PermissionError("附件归属不匹配")
    if row.scene != scene:
        raise PermissionError("附件 scene 不匹配")
    if row.conversation_id != conversation_id:
        raise PermissionError("附件会话不匹配")
    if row.status != AttachmentStatus.UPLOADED.value:
        raise ValueError("附件未就绪")
    if row.mime_type not in MODEL_ATTACHMENT_ALLOWED_MIME_TYPES:
        raise ValueError("附件 MIME 不允许送入模型")
    if scene == AttachmentScene.CHARACTER_CHAT.value:
        if character_id and row.character_id != character_id:
            raise PermissionError("附件角色不匹配")


def read_attachment_bytes_for_model(row: Attachment) -> bytes:
    """读取附件原始字节（送入模型前用）。"""
    local_storage_service.validate_object_key_strict(
        row.object_key,
        scene=row.scene,
        conversation_id=row.conversation_id,
    )
    return local_storage_service.read_bytes(row.object_key)


def build_image_data_uris_for_attachment_ids(
    db: Session,
    attachment_ids: list[str],
    *,
    anon_user_id: str,
    scene: str,
    conversation_id: str,
    character_id: str | None,
) -> list[str]:
    """按 attachment_ids 顺序返回图片 data URI（调用模型前使用）。"""
    out: list[str] = []
    for aid in attachment_ids:
        row = db.get(Attachment, aid)
        if row is None:
            raise ValueError(f"附件不存在: {aid}")
        _validate_row_for_model(
            row,
            anon_user_id=anon_user_id,
            scene=scene,
            conversation_id=conversation_id,
            character_id=character_id,
        )
        data = read_attachment_bytes_for_model(row)
        out.append(build_image_data_uri(row.mime_type, data))
    return out


def ensure_character_chat_attachments_ready(
    db: Session,
    *,
    anon_user_id: str,
    character_id: str,
    draft_turn_id: str,
    attachment_ids: list[str],
) -> None:
    """发送角色聊天前校验：归属、scene、会话（MVP conversation_id=character_id）、已上传、草稿轮一致。"""
    if not attachment_ids:
        return
    conv = character_id  # MVP：一线一角；未来多会话时需独立 conversation_id
    for aid in attachment_ids:
        row = db.get(Attachment, aid)
        if row is None:
            raise ValueError(f"附件不存在: {aid}")
        if row.user_id != anon_user_id:
            raise PermissionError("无权使用该附件")
        if row.scene != AttachmentScene.CHARACTER_CHAT.value:
            raise ValueError("附件 scene 错误")
        if row.conversation_id != conv:
            raise ValueError("附件会话不匹配")
        if row.character_id != character_id:
            raise ValueError("附件角色不匹配")
        if row.draft_turn_id != draft_turn_id:
            raise ValueError("附件草稿轮不匹配")
        if row.message_id is not None:
            raise ValueError("附件已绑定消息")
        if row.status != AttachmentStatus.UPLOADED.value:
            raise ValueError("附件尚未上传完成")


def bind_attachments_to_message(
    db: Session,
    *,
    anon_user_id: str,
    attachment_ids: list[str],
    message_id: str,
    scene: str,
    conversation_id: str,
    character_id: str | None,
) -> None:
    """落库后绑定 message_id，清空 draft_turn_id。"""
    if not attachment_ids:
        return
    for aid in attachment_ids:
        row = db.get(Attachment, aid)
        if row is None:
            raise ValueError(f"附件不存在: {aid}")
        if row.user_id != anon_user_id:
            raise PermissionError("无权绑定附件")
        if row.scene != scene:
            raise ValueError("scene 不匹配")
        if row.conversation_id != conversation_id:
            raise ValueError("conversation 不匹配")
        if character_id and row.character_id != character_id:
            raise ValueError("角色不匹配")
        if row.message_id is not None:
            raise ValueError("附件已绑定")
        row.message_id = message_id
        row.draft_turn_id = None
    db.commit()


def ensure_persona_attachment_rows_ready(
    db: Session,
    *,
    anon_user_id: str,
    conversation_id: str,
    attachment_ids: list[str],
    draft_turn_id: str,
) -> None:
    """人设创建对话单轮发送前校验附件。"""
    if not attachment_ids:
        return
    for aid in attachment_ids:
        row = db.get(Attachment, aid)
        if row is None:
            raise ValueError(f"附件不存在: {aid}")
        if row.user_id != anon_user_id:
            raise PermissionError("无权使用该附件")
        if row.scene != AttachmentScene.PERSONA_CREATION.value:
            raise ValueError("附件 scene 错误")
        if row.conversation_id != conversation_id:
            raise ValueError("附件会话不匹配")
        if row.draft_turn_id != draft_turn_id:
            raise ValueError("附件草稿轮不匹配")
        if row.message_id is not None:
            raise ValueError("附件已绑定消息")
        if row.status != AttachmentStatus.UPLOADED.value:
            raise ValueError("附件尚未上传完成")
