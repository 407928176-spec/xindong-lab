"""GET /api/personas/{id}：详情可见层。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.enums import PersonaCreationMethod
from app.models.persona import Persona
from app.models.user import User


def _memory_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.base import Base

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)


def _make_test_user(factory, uid: str) -> User:
    db = factory()
    user = User(id=uid, username="detailtest")
    db.add(user)
    db.commit()
    db.close()
    return user


def test_persona_detail_flat_fallback() -> None:
    factory = _memory_session_factory()
    uid = str(uuid.uuid4())
    _make_test_user(factory, uid)
    db = factory()

    p = Persona(
        user_id=uid,
        creation_method=PersonaCreationMethod.TEXT_DESCRIPTION.value,
        display_name="卡片点入测",
        identity_summary="身份摘要",
        personality_summary="性格摘要",
        interests="跑步",
        chat_style="偏短句",
        visible_background="同城同学",
        hidden_initial_tendency="",
        hidden_impression_baseline="",
        hidden_key_judgment="",
        hidden_pacing_tolerance="",
        hidden_sensitivity_points="",
        extract_snapshot=None,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    db.close()

    def _override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def _override_get_current_user():
        db = factory()
        try:
            return db.get(User, uid)
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    try:
        with TestClient(app) as client:
            res = client.get(f"/api/personas/{p.id}")
            assert res.status_code == 200
            body = res.json()
            assert body["display_name"] == "卡片点入测"
            assert body["visible_layer"]["display_name"] == "卡片点入测"
            assert "身份摘要" in str(body["visible_layer"]["explicit_personality_notes"])
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_persona_detail_404() -> None:
    factory = _memory_session_factory()
    uid = str(uuid.uuid4())
    _make_test_user(factory, uid)

    def _override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def _override_get_current_user():
        db = factory()
        try:
            return db.get(User, uid)
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    try:
        with TestClient(app) as client:
            res = client.get("/api/personas/00000000-0000-4000-8000-000000000000")
            assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
