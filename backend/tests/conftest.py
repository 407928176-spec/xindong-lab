"""保证从仓库任意工作目录调用 pytest 时，都能 import `app.*`。"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_root = str(_BACKEND_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)

# 把测试数据库指向临时文件。必须在 import 任何 app.db.* 之前设置——引擎是在
# app.db.session 导入时按 DATABASE_URL 建好的，之后再改就晚了。
#
# 两个目的：
# 1. 不碰玩家的真实存档 backend/data/app.db（跑个测试把人存档写脏了说不过去）；
# 2. 全新 clone 下来还没建过库时，pytest 也能直接跑通——不然贡献者第一件事就撞墙。
_TEST_DB = Path(tempfile.gettempdir()) / "xindong_lab_pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

import app.dotenv_load  # noqa: E402, F401 — pytest 直接 import llm_client 前加载 backend/.env


def pytest_sessionstart(session) -> None:
    """每次 pytest 启动都用一个全新的空库建表，避免上次遗留的数据/旧表结构干扰。"""
    _TEST_DB.unlink(missing_ok=True)

    import app.models  # noqa: F401, PLC0415 — 导入 side-effect：注册全部 ORM 模型
    from app.db.session import engine, get_base_metadata  # noqa: PLC0415

    get_base_metadata().create_all(bind=engine)


@pytest.fixture(autouse=True)
def _isolate_llm_config(monkeypatch, tmp_path):
    """把 LLM 配置指向临时文件，并写入一份假配置。

    autouse 是刻意的：单测绝不该读到开发者本机真实的 llm_config.json / 环境变量，
    否则测试结果会因人而异，最坏情况还会拿真 Key 打真实接口花钱。

    这里写真实文件而不是 patch ``load``，是为了让 ``load`` 本身也保持可测——
    测配置层的用例只要把 ``config_path`` 指到别的空目录即可。
    """
    import json

    from app.config import llm_config

    path = tmp_path / "llm_config.json"
    path.write_text(
        json.dumps(
            {
                "base_url": "https://llm.test.invalid/v1",
                "api_key": "test-key-not-real",
                "model": "test-chat-model",
                "aux_model": "test-aux-model",
                "web_search_supported": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(llm_config, "config_path", lambda: path)
    for var in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_AUX_MODEL"):
        monkeypatch.delenv(var, raising=False)

    llm_config.invalidate_cache()
    yield
    llm_config.invalidate_cache()


@pytest.fixture
def character_chat_api_client(monkeypatch):
    """内存 SQLite + 覆盖 SessionLocal/get_db，使 /chat 与图内节点与同一库对话。"""
    import app.models  # noqa: F401 — 注册 ORM
    from app.api.deps import get_current_user, get_current_user_id_streaming, get_db
    from app.db.base import Base
    from app.main import app
    from app.models.character import Character
    from app.models.enums import CharacterStatus
    from app.models.persona import Persona
    from app.models.user import User
    from fastapi.testclient import TestClient

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)

    uid, pid, cid = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    seed = test_local()
    test_user = User(id=uid, username="testuser")
    persona = Persona(
        id=pid,
        user_id=uid,
        display_name="API测人设",
        identity_summary="学生",
        personality_summary="中性",
        interests="画画",
        chat_style="短句",
        visible_background="校园",
        hidden_initial_tendency="慢热",
        hidden_impression_baseline="普通朋友",
        hidden_key_judgment="观望",
        hidden_pacing_tolerance="中等",
        hidden_sensitivity_points="隐私",
    )
    char = Character(
        id=cid,
        user_id=uid,
        persona_id=pid,
        display_name="API测角色",
        status=CharacterStatus.IN_PROGRESS.value,
        hidden_state_snapshot={
            "comfort": 60.0,
            "interest": 55.0,
            "trust": 50.0,
            "alertness": 25.0,
            "baseline_compatibility": 50.0,
        },
    )
    seed.add(test_user)
    seed.add(persona)
    seed.add(char)
    seed.commit()
    seed.close()

    monkeypatch.setattr("app.db.session.SessionLocal", test_local)
    monkeypatch.setattr("app.engine.nodes.save_and_respond.SessionLocal", test_local)
    monkeypatch.setattr("app.engine.nodes.load_context.SessionLocal", test_local)
    monkeypatch.setattr("app.api.deps.SessionLocal", test_local)
    monkeypatch.setattr("app.services.character_service.SessionLocal", test_local)

    def _override_get_db():
        db = test_local()
        try:
            yield db
        finally:
            db.close()

    def _override_get_current_user():
        db = test_local()
        try:
            return db.get(User, uid)
        finally:
            db.close()

    def _override_get_current_user_id_streaming():
        return uid

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_current_user_id_streaming] = _override_get_current_user_id_streaming

    with TestClient(app) as client:
        yield client, cid

    app.dependency_overrides.clear()


@pytest.fixture
def api_client():
    """内存 SQLite 的 TestClient，已种入本地玩家。"""
    import app.models  # noqa: F401 — 注册所有 ORM 模型

    from app.api.deps import get_db
    from app.db.base import Base
    from app.main import app
    from app.models.user import LOCAL_USER_ID, LOCAL_USER_NAME, User
    from fastapi.testclient import TestClient

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)

    seed = local()
    seed.add(User(id=LOCAL_USER_ID, username=LOCAL_USER_NAME))
    seed.commit()
    seed.close()

    def _override_db():
        db = local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides.clear()
