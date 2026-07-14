"""测试 delete_persona 新语义与 delete-preview 端点。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — 注册 ORM
from app.db.base import Base
from app.main import app
from app.models.character import Character
from app.models.ending import Ending
from app.models.enums import CharacterStatus, EndingKind
from app.models.persona import Persona
from app.models.user import User


@pytest.fixture
def db_client(monkeypatch):
    """内存 SQLite + 含三种状态角色（进行中、已结局、回收站）的 Persona fixture。"""
    from app.api.deps import get_current_user, get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)

    uid = str(uuid.uuid4())
    pid = str(uuid.uuid4())
    cid_active = str(uuid.uuid4())   # 进行中（首页可见）
    cid_ended = str(uuid.uuid4())    # 已结局（缘散录）
    cid_archived = str(uuid.uuid4()) # 已在回收站

    seed = TestSession()
    test_user = User(id=uid, username="deletetest")
    persona = Persona(
        id=pid,
        user_id=uid,
        display_name="测试人设",
        identity_summary="",
        personality_summary="",
        interests="",
        chat_style="",
        visible_background="",
        hidden_initial_tendency="",
        hidden_impression_baseline="",
        hidden_key_judgment="",
        hidden_pacing_tolerance="",
        hidden_sensitivity_points="",
    )
    char_active = Character(
        id=cid_active,
        user_id=uid,
        persona_id=pid,
        display_name="进行中角色",
        status=CharacterStatus.IN_PROGRESS.value,
        heartbeat_score=50,
    )
    char_ended = Character(
        id=cid_ended,
        user_id=uid,
        persona_id=pid,
        display_name="已结局角色",
        status=CharacterStatus.ENDED.value,
        heartbeat_score=80,
    )
    ending = Ending(
        id=str(uuid.uuid4()),
        character_id=cid_ended,
        ending_kind=EndingKind.CONFESSION_SUCCESS.value,
        content="圆满",
    )
    char_archived = Character(
        id=cid_archived,
        user_id=uid,
        persona_id=pid,
        display_name="回收站角色",
        status=CharacterStatus.IN_PROGRESS.value,
        heartbeat_score=30,
        deleted_at=datetime.now(tz=timezone.utc),
    )

    seed.add_all([test_user, persona, char_active, char_ended, char_archived, ending])
    seed.commit()
    seed.close()

    monkeypatch.setattr("app.api.deps.SessionLocal", TestSession)

    def _override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def _override_user():
        db = TestSession()
        try:
            return db.get(User, uid)
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app) as client:
        yield client, pid, cid_active, cid_ended, cid_archived, TestSession

    app.dependency_overrides.clear()


class TestDeletePreview:
    def test_returns_three_groups(self, db_client):
        client, pid, cid_active, cid_ended, cid_archived, _ = db_client
        res = client.get(f"/api/personas/{pid}/delete-preview")
        assert res.status_code == 200
        data = res.json()
        assert len(data["active_in_progress"]) == 1
        assert data["active_in_progress"][0]["id"] == cid_active
        assert len(data["ended_characters"]) == 1
        assert data["ended_characters"][0]["id"] == cid_ended
        assert data["ended_characters"][0]["ending_kind"] == EndingKind.CONFESSION_SUCCESS.value
        assert len(data["archived_characters"]) == 1
        assert data["archived_characters"][0]["id"] == cid_archived

    def test_not_found(self, db_client):
        client, *_ = db_client
        res = client.get(f"/api/personas/{uuid.uuid4()}/delete-preview")
        # 不存在（或不属于当前用户）的 persona 返回 404
        assert res.status_code == 404


class TestDeletePersonaNewSemantics:
    def test_blocked_by_active_character(self, db_client):
        """进行中角色存在时，DELETE 应返回 409，三组角色状态不变。"""
        client, pid, cid_active, cid_ended, cid_archived, TestSession = db_client
        res = client.delete(f"/api/personas/{pid}")
        assert res.status_code == 409
        assert "还有角色聊天" in res.json()["detail"]

        # 验证数据库未被修改
        db = TestSession()
        assert db.get(Character, cid_active) is not None
        assert db.get(Character, cid_ended) is not None
        assert db.get(Character, cid_archived) is not None
        from app.models.persona import Persona as P
        p = db.get(P, pid)
        assert p is not None and p.deleted_at is None
        db.close()

    def test_success_without_active_characters(self, db_client):
        """首页无可见角色时，DELETE 应成功：已结局角色进回收站，回收站角色物理删除，人设软删。"""
        client, pid, cid_active, cid_ended, cid_archived, TestSession = db_client

        # 先软删进行中角色（模拟用户在首页删除）
        db = TestSession()
        char_active = db.get(Character, cid_active)
        char_active.deleted_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.close()

        res = client.delete(f"/api/personas/{pid}")
        assert res.status_code == 204

        db = TestSession()
        from app.models.persona import Persona as P

        # 人设已软删
        p = db.get(P, pid)
        assert p is not None and p.deleted_at is not None

        # 已结局角色已物理清除（delete_persona 先软删再统一物理清除）
        assert db.get(Character, cid_ended) is None

        # 原回收站角色物理清除
        assert db.get(Character, cid_archived) is None

        # 原进行中角色（被用户提前软删的）也物理清除
        assert db.get(Character, cid_active) is None
        db.close()

    def test_ending_unread_blocks_deletion(self, db_client):
        """ENDING_UNREAD 状态的角色仍在首页，应阻挡删除。"""
        client, pid, cid_active, cid_ended, _, TestSession = db_client

        # 把进行中角色改成 ENDING_UNREAD（还挂着 ending）
        db = TestSession()
        char = db.get(Character, cid_active)
        char.status = CharacterStatus.ENDING_UNREAD.value
        # 给这个角色也加一个 ending
        ending_unread = Ending(
            id=str(uuid.uuid4()),
            character_id=cid_active,
            ending_kind=EndingKind.CONFESSION_FAIL_CONTINUE.value,
            content="未读结局",
        )
        db.add(ending_unread)
        db.commit()
        db.close()

        res = client.delete(f"/api/personas/{pid}")
        assert res.status_code == 409
