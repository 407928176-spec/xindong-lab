"""静默抽取并入库：mock LLM，不访问方舟。"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — 注册 ORM
from app.api.deps import get_db
from app.db.base import Base
from app.main import app
from app.schemas.persona import ChatMessage, PersonaConfirmGenerateRequest
from app.schemas.persona_extract_v06 import default_persona_extract_v06
from app.services import persona_service

_CONV = "b0000001-0001-4001-8001-000000000001"


def _memory_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)


def _fake_extract_json(display_name: str = "接口测") -> str:
    ex = default_persona_extract_v06()
    ex.visible_layer.display_name = display_name
    return json.dumps(ex.model_dump(mode="json"), ensure_ascii=False)


def test_confirm_generate_service_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _memory_session_factory()
    db = factory()

    monkeypatch.setattr(persona_service, "read_prompt", lambda _: "silent extract system stub")
    monkeypatch.setattr(
        persona_service,
        "call_llm",
        lambda *a, **k: _fake_extract_json("服务侧名"),
    )

    msgs = [ChatMessage(role="user", content="她叫小雅，喜欢跑步")]
    user_id = str(uuid.uuid4())
    payload = PersonaConfirmGenerateRequest(messages=msgs, conversation_id=_CONV)
    out = persona_service.confirm_generate_persona(db, payload, user_id=user_id)
    assert out.id
    assert out.extract.visible_layer.display_name == "服务侧名"


def test_confirm_generate_api_http(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.deps import get_current_user
    from app.models.user import User

    factory = _memory_session_factory()

    monkeypatch.setattr(persona_service, "read_prompt", lambda _: "silent extract system stub")
    monkeypatch.setattr(
        persona_service,
        "call_llm",
        lambda *a, **k: _fake_extract_json("HTTP测"),
    )

    uid = str(uuid.uuid4())
    db = factory()
    db.add(User(id=uid, username="confirmtest"))
    db.commit()
    db.close()

    def _override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

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
            res = client.post(
                "/api/personas/confirm-generate",
                json={
                    "messages": [{"role": "user", "content": "测试用户描述足够长"}],
                    "conversation_id": _CONV,
                },
            )
            assert res.status_code == 201
            body = res.json()
            assert body["id"]
            assert body["extract"]["visible_layer"]["display_name"] == "HTTP测"
    finally:
        app.dependency_overrides.clear()


def test_confirm_generate_no_user_message_400() -> None:
    factory = _memory_session_factory()
    db = factory()
    user_id = str(uuid.uuid4())
    payload = PersonaConfirmGenerateRequest(
        messages=[ChatMessage(role="assistant", content="仅有助手")],
        conversation_id=_CONV,
    )
    with pytest.raises(ValueError, match="用户|附件"):
        persona_service.confirm_generate_persona(db, payload, user_id=user_id)
