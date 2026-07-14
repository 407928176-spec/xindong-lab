"""附件：object_key 与业务会话绑定。

``object_key`` 是相对 ``backend/data/uploads/`` 的相对路径，见
``app/services/local_storage_service.py``。数据库里只存这个键，不存绝对路径——
玩家把整个游戏目录搬走或改名后，附件依然能找到。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AttachmentStatus, AttachmentStorageProvider


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scene: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    character_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    draft_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    file_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    file_ext: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    storage_provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AttachmentStorageProvider.LOCAL.value,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AttachmentStatus.PENDING.value,
        index=True,
    )

    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
