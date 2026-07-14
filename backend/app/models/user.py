"""本地用户模型。

开源版是单机游戏，没有注册登录：整个库里恒定只有一行「本地玩家」，由
``scripts/init_db.py`` 种入，见 :data:`LOCAL_USER_ID`。

保留 ``users`` 表而不是把 ``user_id`` 外键全部拆掉，是因为人设、角色、消息、附件都
挂在它下面；留着这一层既不增加玩家的使用成本，也让将来想自己加多用户/联机的人有
现成的接入点。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 固定的本地玩家 ID。单机模式下所有数据都归属这个用户。
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_USER_NAME = "本地玩家"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: LOCAL_USER_ID)
    username: Mapped[str] = mapped_column(String(32), nullable=False, default=LOCAL_USER_NAME)

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
