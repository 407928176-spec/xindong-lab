"""附件 API 的请求 / 响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadAttachmentResponse(BaseModel):
    """单次上传的结果。前端拿 ``attachment_id`` 随消息一起发送。"""

    attachment_id: str
    file_name: str = Field(default="", description="原始文件名，气泡胶囊展示用")
    mime_type: str = Field(default="", description="MIME，用于判断是否以内联缩略图展示")
    size: int = 0
    status: str


class AttachmentMetaItem(BaseModel):
    """附件元信息。内容本身走 ``GET /api/attachments/{id}/content``。"""

    attachment_id: str
    file_name: str = ""
    mime_type: str = ""
    size: int = 0


class AttachmentMetaResponse(BaseModel):
    items: list[AttachmentMetaItem]
