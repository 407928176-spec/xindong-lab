"""角色与角色对话 API 的请求 / 响应模型（阶段 4：mock 回复，不入 LangGraph）。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator
import uuid


class CharacterCreateRequest(BaseModel):
    """从已保存的人设创建一条新的角色关系线。"""

    persona_id: str = Field(..., min_length=1, max_length=36)
    display_name: str | None = Field(
        default=None,
        max_length=128,
        description="可选；省略则使用人设的 display_name",
    )


class CharacterCreatedResponse(BaseModel):
    """创建角色后的最小回执。"""

    id: str
    persona_id: str
    display_name: str
    heartbeat_score: int
    message: str = Field(default="created")


class CharacterMessageItem(BaseModel):
    """单条持久化消息；role 与 MessageRole 一致（角色侧为 character）。"""

    id: str
    role: Literal["user", "character"]
    content: str
    round_number: int
    created_at: datetime
    is_no_reply: bool = Field(default=False, description="角色主动沉默轮（非模型故障）")
    message_type: Literal["normal", "no_reply"] = Field(default="normal")
    display_text: str = Field(
        default="",
        description="前端展示用；no_reply 时为固定文案，可与 content 不同",
    )
    attachment_ids: list[str] = Field(default_factory=list, description="本消息关联的附件 ID（展示用）")


class EndingPayload(BaseModel):
    """终局回包；与 ending_judge 输出字段对齐。"""

    result: str
    evaluation: str
    user_review: str | None = None


class PinToggleResponse(BaseModel):
    """置顶状态切换回执。"""

    is_pinned: bool


class CharacterListItem(BaseModel):
    """首页 / 列表用的角色卡片。"""

    id: str
    display_name: str
    persona_id: str
    persona_display_name: str
    heartbeat_score: int
    status: str
    last_message_preview: str = Field(default="", description="最近一条消息摘要，可能为空")
    updated_at: datetime
    is_pinned: bool = False
    ending: EndingPayload | None = Field(default=None, description="终局结果与评价，仅 ended 角色有值")


class CharacterDetailResponse(BaseModel):
    """角色对话页首屏：元信息 + 历史消息。"""

    id: str
    display_name: str
    persona_id: str
    persona_display_name: str
    heartbeat_score: int
    status: str
    messages: list[CharacterMessageItem] = Field(default_factory=list)
    ending: EndingPayload | None = None


class CharacterChatRequest(BaseModel):
    """发送一条用户消息；不要求携带完整历史（由服务端从库读取）。

    MVP：conversation_id 与 ``character_id`` 相同（一线一角）；未来多会话时需独立 conversation_id。
    """

    content: str = Field(default="", max_length=8000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=9)
    draft_turn_id: str = Field(default="", max_length=36)

    @model_validator(mode="after")
    def _content_or_attachments(self) -> CharacterChatRequest:
        has_text = bool(self.content.strip())
        has_att = bool(self.attachment_ids)
        if not has_text and not has_att:
            raise ValueError("至少需要文本内容或附件之一")
        if has_att:
            part = self.draft_turn_id.strip()
            try:
                uuid.UUID(part)
            except ValueError as exc:
                raise ValueError("带附件时必须提供合法 draft_turn_id（UUID）") from exc
        return self


class CharacterChatResponse(BaseModel):
    """LangGraph 跑通并落库后的返回；assistant_message 为角色正文。"""

    assistant_message: str
    user_message: CharacterMessageItem
    assistant_message_item: CharacterMessageItem
    heartbeat_score: int
    round: int
    ending: EndingPayload | None = None
    assistant_no_reply: bool = Field(default=False, description="本轮角色是否无文字回应")
    assistant_display_text: str = Field(
        default="",
        description="本轮 UI 展示文案；沉默时为固定句，否则可与 assistant_message 相同",
    )
    assistant_message_type: Literal["normal", "no_reply"] = Field(default="normal")
