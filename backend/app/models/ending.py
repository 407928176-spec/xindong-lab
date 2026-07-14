"""终局（Ending）模型：一条角色线在收束时的结果记录。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EndingKind


class Ending(Base):
    __tablename__ = "endings"
    __table_args__ = (UniqueConstraint("character_id", name="uq_endings_character_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )

    ending_kind: Mapped[str] = mapped_column(String(48), nullable=False, default=EndingKind.USER_ARCHIVED.value)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_review: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    character: Mapped["Character"] = relationship(back_populates="ending")
