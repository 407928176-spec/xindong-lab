"""人设相关 API 的请求 / 响应模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.config.attachment_policy import MAX_ATTACHMENTS_PER_MESSAGE
from app.schemas.persona_extract_v06 import PersonaExtractV06, VisibleLayerV06


class ChatMessage(BaseModel):
    """单条对话消息（人设创建交互）；允许正文为空以便「仅附件」轮通过外层 attachment_ids 表达。"""

    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=8000)


class PersonaChatRequest(BaseModel):
    """人设创建对话请求：messages + 客户端会话 UUID + 本轮草稿 UUID；可选附件。"""

    messages: list[ChatMessage] = Field(default_factory=list)
    conversation_id: str = Field(..., min_length=36, max_length=36, description="人设创建会话 ID（与 presign conversation_id 一致）")
    draft_turn_id: str = Field(..., min_length=36, max_length=36, description="本轮草稿 UUID（每轮发送换新）")
    attachment_ids: list[str] = Field(default_factory=list, max_length=MAX_ATTACHMENTS_PER_MESSAGE)

    @model_validator(mode="after")
    def _validate_chat_turn(self) -> PersonaChatRequest:
        if not self.messages:
            raise ValueError("messages 不能为空")
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须是 user，表示用户刚发送的内容")
        try:
            uuid.UUID(self.conversation_id.strip())
            uuid.UUID(self.draft_turn_id.strip())
        except ValueError as exc:
            raise ValueError("conversation_id / draft_turn_id 必须为合法 UUID") from exc
        last = self.messages[-1]
        has_text = bool(last.content.strip())
        has_att = bool(self.attachment_ids)
        if not has_text and not has_att:
            raise ValueError("至少需要文本内容或附件之一")
        return self


class PersonaConfirmGenerateRequest(BaseModel):
    """静默抽取 JSON：除 transcript 外需会话 ID 以聚合该会话全部附件。"""

    messages: list[ChatMessage] = Field(default_factory=list)
    conversation_id: str = Field(..., min_length=36, max_length=36)

    @model_validator(mode="after")
    def _need_dialog(self) -> PersonaConfirmGenerateRequest:
        if not self.messages:
            raise ValueError("messages 不能为空")
        try:
            uuid.UUID(self.conversation_id.strip())
        except ValueError as exc:
            raise ValueError("conversation_id 必须为合法 UUID") from exc
        return self


class PersonaChatResponse(BaseModel):
    """人设创建对话响应：智能体回复 + persona_extract_v0.6 快照（前端可见层）。"""

    assistant_message: str = Field(..., description="智能体自然语言回复，仅用于聊天区")
    extract: PersonaExtractV06 = Field(..., description="最新一轮推导的人设抽取结构")


class PersonaSaveRequest(BaseModel):
    """保存人设：对话记录与已通过校验的 persona_extract_v0.6。"""

    messages: list[ChatMessage] = Field(default_factory=list)
    extract: PersonaExtractV06


class PersonaCreatedResponse(BaseModel):
    """创建成功后的最小回执。"""

    id: str
    message: str = Field(default="created")


class PersonaConfirmGenerateResponse(BaseModel):
    """静默抽取并入库。"""

    id: str
    extract: PersonaExtractV06
    message: str = Field(default="created")


class PinToggleResponse(BaseModel):
    """置顶状态切换回执。"""

    is_pinned: bool


class PersonaListItem(BaseModel):
    """人设库列表项。"""

    id: str
    display_name: str
    identity_summary: str
    created_at: datetime
    is_pinned: bool = False
    active_character_count: int = 0


class PersonaDetailResponse(BaseModel):
    """单人设详情：可见层（优先 extract_snapshot）。"""

    id: str
    display_name: str
    created_at: datetime
    visible_layer: VisibleLayerV06


class PersonaDeletePreviewItem(BaseModel):
    """删除预览中单个角色的最小信息。"""

    id: str
    display_name: str
    updated_at: datetime
    ending_kind: str | None = None


class PersonaDeletePreviewResponse(BaseModel):
    """删除人设前的影响预览：三组角色分类。"""

    active_in_progress: list[PersonaDeletePreviewItem]
    ended_characters: list[PersonaDeletePreviewItem]
    archived_characters: list[PersonaDeletePreviewItem]
