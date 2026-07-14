"""数据库配置：默认 SQLite 文件路径，可用环境变量覆盖。"""

from __future__ import annotations

import os
from pathlib import Path


def get_database_url() -> str:
    """返回 SQLAlchemy 使用的数据库 URL。

    优先读取环境变量 `DATABASE_URL`；未设置时使用 `backend/data/app.db`。
    将文件路径放在 `backend/data/` 下，避免与代码混在一起，也便于 .gitignore。
    """
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit

    backend_root = Path(__file__).resolve().parents[2]
    data_dir = backend_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "app.db"
    # 三斜杠表示相对/绝对文件路径；POSIX 形式在 Windows 上也可被 SQLAlchemy 正确处理
    return f"sqlite:///{db_path.as_posix()}"
