"""角色（Character）模型：人设派生实例，承载心动值与隐藏状态等。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CharacterStatus


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    persona_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("personas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CharacterStatus.IN_PROGRESS.value,
    )

    heartbeat_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))

    # 多个隐藏维度的结构化快照；阶段 5 前后由规则引擎与状态更新链路写入
    hidden_state_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 角色专属 persona 提示词：阶段 5 由 persona_generator 写入；为空时 load_context 回退人设表拼装
    persona_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 长期记忆摘要：阶段 5 才会真正写入；阶段 2 仅占位字段
    long_term_memory: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 上次更新长期记忆摘要时对应的对话轮次；默认从 0 开始
    memory_updated_at_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    is_ended: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    persona: Mapped["Persona"] = relationship(back_populates="characters")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
    )
    ending: Mapped["Ending | None"] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        uselist=False,
    )
