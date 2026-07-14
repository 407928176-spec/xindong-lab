"""人设创建对话：mock LLM，不访问方舟。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.models.user import User
from app.schemas.persona import ChatMessage, PersonaChatRequest
from app.services import persona_service

_CONV = "a0000001-0001-4001-8001-000000000001"
_DRAFT = "a0000002-0002-4002-8002-000000000002"

_FAKE_USER = User(id="00000000-0000-0000-0000-000000000001", username="testuser")


def _bypass_auth() -> None:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER


def _restore_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def test_handle_persona_chat_returns_assistant_from_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(persona_service, "read_prompt", lambda _: "chat system stub")
    monkeypatch.setattr(
        persona_service,
        "call_llm",
        lambda messages, **kwargs: "助手回复来自 mock LLM",
    )

    payload = PersonaChatRequest(
        messages=[ChatMessage(role="user", content="她喜欢跑步")],
        conversation_id=_CONV,
        draft_turn_id=_DRAFT,
    )
    out = persona_service.handle_persona_chat(payload)
    assert out.assistant_message == "助手回复来自 mock LLM"
    assert out.extract.visible_layer.display_name  # mock extract still populated


def test_persona_chat_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(persona_service, "read_prompt", lambda _: "chat system stub")
    monkeypatch.setattr(
        persona_service,
        "call_llm",
        lambda messages, **kwargs: "HTTP 侧助手句",
    )

    _bypass_auth()
    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/personas/chat",
                json={
                    "messages": [{"role": "user", "content": "简短描述"}],
                    "conversation_id": _CONV,
                    "draft_turn_id": _DRAFT,
                },
            )
            assert res.status_code == 200
            body = res.json()
            assert body["assistant_message"] == "HTTP 侧助手句"
            assert body["extract"]["visible_layer"]
    finally:
        _restore_auth()


def test_persona_chat_llm_failure_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(persona_service, "read_prompt", lambda _: "chat system stub")

    def _boom(*a, **k):
        raise ConnectionError("upstream")

    monkeypatch.setattr(persona_service, "call_llm", _boom)

    _bypass_auth()
    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/personas/chat",
                json={
                    "messages": [{"role": "user", "content": "测"}],
                    "conversation_id": _CONV,
                    "draft_turn_id": _DRAFT,
                },
            )
            assert res.status_code == 502
            assert "人设创建对话模型调用失败" in res.json().get("detail", "")
    finally:
        _restore_auth()


def test_persona_chat_stream_sse_contains_done(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(persona_service, "read_prompt", lambda _: "stub sys")

    def fake_llm(*args, **kwargs):
        if kwargs.get("stream"):

            def gen():
                yield "流"
                yield "式"

            return gen()
        return "流式"

    monkeypatch.setattr(persona_service, "call_llm", fake_llm)

    _bypass_auth()
    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/personas/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "conversation_id": _CONV,
                    "draft_turn_id": _DRAFT,
                },
            )
            assert res.status_code == 200
            assert "event-stream" in res.headers.get("content-type", "")
            body = res.text
            assert "token" in body
            assert "done" in body
            assert "流式" in body
    finally:
        _restore_auth()
