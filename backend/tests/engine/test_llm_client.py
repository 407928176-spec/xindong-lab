from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import llm_config
from app.engine import llm_client


def _cfg(**overrides) -> llm_config.LlmConfig:
    base = {
        "base_url": "https://llm.test.invalid/v1",
        "api_key": "fake-key",
        "model": "fake-chat-model",
        "aux_model": "fake-aux-model",
    }
    base.update(overrides)
    return llm_config.LlmConfig(**base)


def _patch_cfg(cfg: llm_config.LlmConfig):
    return patch.object(llm_config, "load", lambda: cfg)


def test_call_llm_non_stream_returns_assistant_text() -> None:
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = "  hello  "

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg()):
            out = llm_client.call_llm(
                [{"role": "user", "content": "ping"}],
                temperature=0.5,
                stream=False,
            )

    assert out == "hello"
    call_kw = mock_client.chat.completions.create.call_args.kwargs
    assert call_kw["messages"] == [{"role": "user", "content": "ping"}]
    assert call_kw["temperature"] == 0.5
    assert call_kw.get("stream", False) is False


def test_call_llm_stream_yields_chunks() -> None:
    c1, c2 = MagicMock(), MagicMock()
    for c, text in ((c1, "a"), (c2, "b")):
        c.choices = [MagicMock()]
        c.choices[0].delta = MagicMock()
        c.choices[0].delta.content = text

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([c1, c2])

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg()):
            gen = llm_client.call_llm([{"role": "user", "content": "x"}], stream=True)
            joined = "".join(gen)

    assert joined == "ab"
    assert mock_client.chat.completions.create.call_args.kwargs["stream"] is True


def test_call_llm_explicit_model_kwarg() -> None:
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = "ok"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg()):
            llm_client.call_llm([{"role": "user", "content": "p"}], stream=False, model="summary-model-x")

    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "summary-model-x"


def test_auxiliary_credentials_selects_aux_model() -> None:
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = "aux"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg()):
            out = llm_client.call_llm(
                [{"role": "user", "content": "q"}],
                stream=False,
                use_auxiliary_credentials=True,
            )

    assert out == "aux"
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "fake-aux-model"


def test_aux_model_falls_back_to_main_model_when_unset() -> None:
    with _patch_cfg(_cfg(aux_model="")):
        assert llm_client.get_auxiliary_model() == "fake-chat-model"
        assert llm_client.get_summary_model() == "fake-chat-model"
        assert llm_client.get_extract_model() == "fake-chat-model"


def test_raises_when_not_configured() -> None:
    with _patch_cfg(llm_config.LlmConfig()):
        with pytest.raises(ValueError, match="尚未配置大模型"):
            llm_client.call_llm([{"role": "user", "content": "x"}])


# --- 厂商兼容性：thinking 参数只能发给方舟 -------------------------------------
# 这是最容易让非方舟供应商 400 的地方，值得单独钉死。


def _capture_extra_body(base_url: str) -> dict:
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = "x"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg(base_url=base_url)):
            llm_client.call_llm([{"role": "user", "content": "x"}], stream=False)

    return mock_client.chat.completions.create.call_args.kwargs["extra_body"]


def test_ark_endpoint_gets_thinking_disabled() -> None:
    extra = _capture_extra_body("https://ark.cn-beijing.volces.com/api/v3")
    assert extra == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://api.deepseek.com/v1",
        "http://localhost:11434/v1",
    ],
)
def test_non_ark_endpoints_get_no_vendor_specific_params(base_url: str) -> None:
    """OpenAI 等标准端点收到未知字段会直接 400，extra_body 必须为空。"""
    assert _capture_extra_body(base_url) == {}


def test_web_search_ignored_when_not_supported() -> None:
    """非方舟端点即使传 use_web_search=True，也必须走普通补全而不是 /responses。"""
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = "x"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg(base_url="https://api.openai.com/v1", web_search_supported=False)):
            llm_client.call_llm([{"role": "user", "content": "x"}], stream=False, use_web_search=True)

    mock_client.chat.completions.create.assert_called_once()
    mock_client.responses.create.assert_not_called()


def test_web_search_not_used_on_non_ark_even_if_flag_true() -> None:
    """配置里 web_search_supported 为 True 但端点不是方舟时，仍不得走 /responses。

    这能防住「先用方舟探测通过、后来把 Base URL 改成 OpenAI」留下的脏状态。
    """
    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = "x"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_completion

    with patch.object(llm_client, "create_sync_client", return_value=mock_client):
        with _patch_cfg(_cfg(base_url="https://api.openai.com/v1", web_search_supported=True)):
            llm_client.call_llm([{"role": "user", "content": "x"}], stream=False, use_web_search=True)

    mock_client.responses.create.assert_not_called()
