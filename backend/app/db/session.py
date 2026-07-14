"""数据库引擎与会话工厂。"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.settings import get_database_url


def _sqlite_setup(dbapi_connection, _connection_record) -> None:
    """每条新 SQLite 连接的初始化：外键约束、WAL 日志模式、写锁等待超时、降低 fsync 频率。

    WAL 模式允许读写并发（读不阻塞写），busy_timeout 让写锁竞争时等待而非立即失败，
    synchronous=NORMAL 在 WAL 下安全，减轻慢磁盘/低内存服务器的 fsync 压力。
    journal_mode 是数据库级持久设置，每次连接设置是幂等的。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


DATABASE_URL = get_database_url()

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # 适度放宽连接池上限，留出慢 LLM 调用期间多个请求并发的余量
    pool_size=10 if _is_sqlite else 5,
    max_overflow=20 if _is_sqlite else 10,
    pool_pre_ping=True,
    pool_recycle=1800,
)

if _is_sqlite:
    event.listen(engine, "connect", _sqlite_setup)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)


def get_base_metadata():
    """延迟导入模型，避免循环依赖；供建表脚本使用。"""
    import app.models  # noqa: F401

    return Base.metadata
