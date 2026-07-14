"""初始化数据库：建表 + 种入本地玩家。

用法（在 `backend/` 目录下、已激活虚拟环境）::

    python scripts/init_db.py

本脚本是幂等的，重复执行安全——启动脚本每次都会跑它。
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_root))

    import app.models  # noqa: F401, PLC0415 — 导入 side-effect：把所有 ORM 模型注册到 metadata
    from app.db.session import SessionLocal, engine, get_base_metadata  # noqa: PLC0415
    from app.models.user import LOCAL_USER_ID, LOCAL_USER_NAME, User  # noqa: PLC0415

    get_base_metadata().create_all(bind=engine)
    print("建表完成:", engine.url)

    # 单机模式：全库恒定一个玩家，所有人设/角色/消息都挂在它下面。
    with SessionLocal() as db:
        if db.get(User, LOCAL_USER_ID) is None:
            db.add(User(id=LOCAL_USER_ID, username=LOCAL_USER_NAME))
            db.commit()
            print("已创建本地玩家")
        else:
            print("本地玩家已存在，跳过")


if __name__ == "__main__":
    main()
