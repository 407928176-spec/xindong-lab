"""人设（Persona）模型：模板层，可被多次实例化为角色。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PersonaCreationMethod


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    creation_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PersonaCreationMethod.AI_AUTO.value,
    )

    # --- 用户可见层（PRD 8.2）---
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    identity_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personality_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interests: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chat_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visible_background: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- 系统隐藏层（PRD 8.2；拆字段 + JSON 参数，便于查询与扩展）---
    hidden_initial_tendency: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden_impression_baseline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden_key_judgment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden_pacing_tolerance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden_sensitivity_points: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hidden_evolution_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    raw_source_material: Mapped[str | None] = mapped_column(Text, nullable=True)

    # persona_extract_v0.6 完整快照（单一事实来源）；扁平列为 persona_extract_mapping 派生
    extract_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 由 persona_generator 生成后缓存；第二次创建角色时直接复用，避免重复 LLM 调用
    cached_persona_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 标记 display_name 是否由用户主动指定（False = 模型自主生成，构成去重池）
    name_user_specified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
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

    characters: Mapped[list["Character"]] = relationship(
        back_populates="persona",
        cascade="all, delete-orphan",
    )
