from __future__ import annotations

import pytest

from app.engine.state import minimal_conversation_state
from app.engine.web_context import WebContextBuildResult, insert_web_context_message, needs_web_context


@pytest.fixture
def web_search_on(monkeypatch):
    """默认假配置不支持联网；要测判断逻辑就得先把这道闸打开。"""
    monkeypatch.setattr("app.engine.web_context.web_search_available", lambda: True)


def test_needs_web_context_uses_model_decision(monkeypatch, web_search_on) -> None:
    state = minimal_conversation_state()
    state["user_message"] = "今天的新闻你看了么？"

    monkeypatch.setattr(
        "app.engine.web_context.call_llm",
        lambda *args, **kwargs: '{"should_search": true, "query": "今天 娱乐新闻", "reason": "用户询问实时新闻"}',
    )

    assert needs_web_context(state) is True


def test_needs_web_context_skips_plain_chat_by_model(monkeypatch, web_search_on) -> None:
    state = minimal_conversation_state()
    state["user_message"] = "我今天有点想你"

    monkeypatch.setattr(
        "app.engine.web_context.call_llm",
        lambda *args, **kwargs: '{"should_search": false, "query": "", "reason": "普通情绪聊天"}',
    )

    assert needs_web_context(state) is False


def test_skips_entirely_when_web_search_unsupported(monkeypatch) -> None:
    """供应商不支持联网时，连「要不要联网」都不该问模型——白花一次调用。"""
    state = minimal_conversation_state()
    state["user_message"] = "今天的新闻你看了么？"

    monkeypatch.setattr("app.engine.web_context.web_search_available", lambda: False)

    def fail(*args, **kwargs):
        raise AssertionError("不支持联网时不应调用模型")

    monkeypatch.setattr("app.engine.web_context.call_llm", fail)

    assert needs_web_context(state) is False


def test_insert_web_context_message_before_last_user() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "旧答"},
        {"role": "user", "content": "今天新闻看了吗"},
    ]

    out = insert_web_context_message(messages, WebContextBuildResult("资料包"))

    assert out[-2]["role"] == "system"
    assert "资料包" in out[-2]["content"]
    assert "不要用“你对哪条/哪块/哪方面/哪个方向感兴趣”" in out[-2]["content"]
    assert out[-1] == {"role": "user", "content": "今天新闻看了吗"}
    assert messages[-1] == {"role": "user", "content": "今天新闻看了吗"}


def test_insert_web_context_message_accepts_plain_string() -> None:
    messages = [{"role": "user", "content": "天气怎么样"}]

    out = insert_web_context_message(messages, "天气资料包")

    assert out[-2]["role"] == "system"
    assert "天气资料包" in out[-2]["content"]


def test_attachment_turn_skips_without_model_call(monkeypatch, web_search_on) -> None:
    state = minimal_conversation_state()
    state["pending_attachment_ids"] = ["attachment-id"]

    def fail(*args, **kwargs):
        raise AssertionError("should not call model")

    monkeypatch.setattr("app.engine.web_context.call_llm", fail)

    assert needs_web_context(state) is False
