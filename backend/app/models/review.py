"""复盘（Review）模型：短复盘 / 长复盘记录。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ReviewType


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    character_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    review_type: Mapped[str] = mapped_column(String(16), nullable=False, default=ReviewType.SHORT.value)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 所分析的会话范围，例如 {"from_round": 1, "to_round": 12}
    analyzed_range: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    character: Mapped["Character"] = relationship(back_populates="reviews")
