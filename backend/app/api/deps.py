"""FastAPI 依赖：数据库会话与当前玩家。

开源版是单机游戏，没有注册登录：所有请求都归属同一个本地玩家
（``app.models.user.LOCAL_USER_ID``）。

这里刻意保留了 ``get_current_user`` 这个名字、也保留了「当前用户」这层抽象，而不是
把 ``user_id`` 从各处删掉——一方面路由层写法跟带鉴权时完全一致，另一方面将来谁想
加回多用户或联机，只要换掉这两个函数的实现，路由和 service 都不用动。
"""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import LOCAL_USER_ID, LOCAL_USER_NAME, User


def get_db() -> Generator[Session, None, None]:
    """为每个请求提供独立的数据库会话，并在请求结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_local_user(db: Session) -> User:
    """取本地玩家，不存在就建。

    正常情况下 ``scripts/init_db.py`` 已经种好了。这里兜底是为了应对玩家手动删库、
    或用自定义 ``DATABASE_URL`` 指向一个没跑过初始化的空库——那种情况下直接 500
    对玩家毫无意义，静默补一行就好。
    """
    user = db.get(User, LOCAL_USER_ID)
    if user is None:
        user = User(id=LOCAL_USER_ID, username=LOCAL_USER_NAME)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(db: Session = Depends(get_db)) -> User:
    """当前玩家。单机模式下恒定是本地玩家。"""
    return ensure_local_user(db)


def get_current_user_id_streaming() -> str:
    """SSE 流式接口专用：只要 user_id，不占用数据库会话。

    流式响应会持续很久，依赖里若持有 Session，整条流期间连接都被占着，
    并发几条就能耗尽连接池。
    """
    return LOCAL_USER_ID
