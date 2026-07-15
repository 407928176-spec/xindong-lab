"""大模型连通性探测：别把「没报错」当成「能用」。

这里钉住的是一个真实踩过的坑：Base URL 少了 /v1 时，请求会打到供应商的官网首页，
拿回一个 HTTP 200 的 HTML 页面。openai SDK 遇到非 JSON 响应不抛异常，而是把正文原样
返回。如果探测只 try/except，就会把这份根本用不了的配置报成「连接成功」，玩家进游戏
才会撞上「模型返回为空」。
"""

from __future__ import annotations

from typing import Any

import httpx
import openai
import pytest

from app.config.llm_config import LlmConfig
from app.services import llm_probe_service


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    """一个结构正常的对话补全响应。"""

    def __init__(self, content: str = "hi") -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, result: Any) -> None:
        self._result = result

    def create(self, **_kwargs: Any) -> Any:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeChat:
    def __init__(self, result: Any) -> None:
        self.completions = _FakeCompletions(result)


class _FakeClient:
    """只实现探测用到的那部分 OpenAI 客户端。"""

    def __init__(self, result: Any) -> None:
        self.chat = _FakeChat(result)


@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch):
    """按 base_url 决定返回什么，用来模拟「根路径是网页、/v1 才是接口」的真实网关。"""

    def _install(by_base_url: dict[str, Any], default: Any = "<!doctype html>"):
        seen: list[str] = []

        def _factory(**kwargs: Any) -> _FakeClient:
            base = kwargs.get("base_url", "")
            seen.append(base)
            return _FakeClient(by_base_url.get(base, default))

        monkeypatch.setattr(llm_probe_service, "OpenAI", _factory)
        # 联网探测是方舟私有能力，这里一律按不支持处理，专注于主链路断言。
        monkeypatch.setattr(
            llm_probe_service, "_probe_web_search", lambda _cfg, _client: (False, "")
        )
        return seen

    return _install


def _cfg(base_url: str = "https://gw.example.ai/v1") -> LlmConfig:
    return LlmConfig(base_url=base_url, api_key="sk-test", model="gpt-4o")


def test_normal_completion_passes(patch_client) -> None:
    patch_client({"https://gw.example.ai/v1": _FakeCompletion("hi")})
    result = llm_probe_service.probe(_cfg())
    assert result.ok is True
    assert result.base_url == "https://gw.example.ai/v1"


def test_html_page_triggers_auto_v1_and_succeeds(patch_client) -> None:
    """根路径返回网页时，自动补 /v1 实测通过 → 判定成功，并回传更正后的地址。"""
    patch_client(
        {
            "https://gw.example.ai": "<!doctype html>\n<html>...</html>",
            "https://gw.example.ai/v1": _FakeCompletion("hi"),
        }
    )
    result = llm_probe_service.probe(_cfg("https://gw.example.ai"))
    assert result.ok is True
    assert result.base_url == "https://gw.example.ai/v1"  # 保存时必须用这个
    assert "自动更正" in result.message


def test_404_triggers_auto_v1_and_succeeds(patch_client) -> None:
    """有的网关对错路径返回 404 而不是网页，同样该补 /v1 再试。"""
    not_found = openai.NotFoundError(
        "not found", response=httpx.Response(404, request=httpx.Request("POST", "http://x")), body=None
    )
    patch_client(
        {
            "https://gw.example.ai": not_found,
            "https://gw.example.ai/v1": _FakeCompletion("hi"),
        }
    )
    result = llm_probe_service.probe(_cfg("https://gw.example.ai"))
    assert result.ok is True
    assert result.base_url == "https://gw.example.ai/v1"


def test_auto_v1_not_attempted_when_already_versioned(patch_client) -> None:
    """地址已带版本段（方舟 /api/v3）时不能去拼 /api/v3/v1。"""
    seen = patch_client({}, default="<!doctype html>")
    result = llm_probe_service.probe(_cfg("https://ark.cn-beijing.volces.com/api/v3"))
    assert result.ok is False
    assert not any(b.endswith("/api/v3/v1") for b in seen)


def test_v1_retry_still_html_reports_address_error(patch_client) -> None:
    """补了 /v1 还是网页 → 地址确实不对，如实报地址问题。"""
    patch_client({}, default="<!doctype html>")
    result = llm_probe_service.probe(_cfg("https://gw.example.ai"))
    assert result.ok is False
    assert "https://gw.example.ai" in result.message


def test_v1_retry_surfaces_real_error_behind_bad_address(patch_client) -> None:
    """地址缺 /v1 且 Key 也错时，要直接点出 Key 的问题，别让人先去改地址白跑一轮。"""
    auth_err = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=httpx.Request("POST", "http://x")), body=None
    )
    patch_client(
        {
            "https://gw.example.ai": "<!doctype html>",
            "https://gw.example.ai/v1": auth_err,
        }
    )
    result = llm_probe_service.probe(_cfg("https://gw.example.ai"))
    assert result.ok is False
    assert "API Key" in result.message  # 真正的问题
    assert "/v1" in result.message  # 同时告知地址已被自动补全测试过


def test_auth_error_does_not_trigger_v1_retry(patch_client) -> None:
    """Key 不对就是 Key 不对，不该浪费一次调用去补 /v1。"""
    auth_err = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=httpx.Request("POST", "http://x")), body=None
    )
    seen = patch_client({}, default=auth_err)
    result = llm_probe_service.probe(_cfg("https://gw.example.ai"))
    assert result.ok is False
    assert seen == ["https://gw.example.ai"]  # 只试了一次


def test_incomplete_config_rejected() -> None:
    result = llm_probe_service.probe(LlmConfig(base_url="", api_key="", model=""))
    assert result.ok is False
