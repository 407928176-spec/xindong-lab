"""大模型配置层：存取、环境变量覆盖、方舟识别、Key 脱敏。"""

from __future__ import annotations

import pytest

from app.config import llm_config


@pytest.fixture
def cfg_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """把配置文件指向一个全新的空目录（绕开 conftest 里种的那份假配置）。"""
    path = tmp_path / "isolated" / "llm_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(llm_config, "config_path", lambda: path)
    for var in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_AUX_MODEL"):
        monkeypatch.delenv(var, raising=False)
    llm_config.invalidate_cache()
    yield path
    llm_config.invalidate_cache()


def test_unconfigured_by_default(cfg_file) -> None:
    assert llm_config.is_configured() is False


def test_save_then_load_roundtrip(cfg_file) -> None:
    llm_config.save(
        llm_config.LlmConfig(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4o",
            web_search_supported=False,
        )
    )
    got = llm_config.load()
    assert got.base_url == "https://api.openai.com/v1"
    assert got.api_key == "sk-test"
    assert got.model == "gpt-4o"
    assert llm_config.is_configured() is True


def test_env_overrides_file(cfg_file, monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量优先级高于向导写的文件——服务器部署要靠这个绕过向导。"""
    llm_config.save(
        llm_config.LlmConfig(base_url="https://from-file/v1", api_key="file-key", model="file-model")
    )
    monkeypatch.setenv("LLM_MODEL", "env-model")
    llm_config.invalidate_cache()

    got = llm_config.load()
    assert got.model == "env-model"
    # 没被环境变量覆盖的字段仍然来自文件
    assert got.api_key == "file-key"


def test_env_base_url_change_resets_stale_web_search_flag(cfg_file, monkeypatch: pytest.MonkeyPatch) -> None:
    """用环境变量把端点从方舟改成 OpenAI 后，不能带着旧的联网探测结果。"""
    llm_config.save(
        llm_config.LlmConfig(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="k",
            model="m",
            web_search_supported=True,
        )
    )
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_config.invalidate_cache()

    assert llm_config.load().web_search_supported is False


def test_corrupt_config_file_falls_back_to_unconfigured(cfg_file) -> None:
    """配置文件损坏不能让后端起不来——玩家会被向导接住重填。"""
    cfg_file.write_text("{not valid json", encoding="utf-8")
    llm_config.invalidate_cache()
    assert llm_config.is_configured() is False


def test_incomplete_config_is_not_configured(cfg_file) -> None:
    llm_config.save(llm_config.LlmConfig(base_url="https://x/v1", api_key="k", model=""))
    assert llm_config.is_configured() is False


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://ark.cn-beijing.volces.com/api/v3", True),
        ("https://ark.ap-southeast.volces.com/api/v3", True),
        ("https://api.openai.com/v1", False),
        ("https://api.deepseek.com/v1", False),
        ("http://localhost:11434/v1", False),
        # 只看 host，不能被 path/query 里的关键字骗过去
        ("https://evil.example.com/?next=ark.cn-beijing.volces.com", False),
        ("https://evil.example.com/volces.com/v1", False),
        ("", False),
        ("not-a-url", False),
    ],
)
def test_is_ark_endpoint(url: str, expected: bool) -> None:
    assert llm_config.is_ark_endpoint(url) is expected


def test_masked_api_key_never_leaks_body() -> None:
    masked = llm_config.masked_api_key("sk-abcdefghijklmnop1234")
    assert masked == "sk-a********1234"
    assert "efghijklmnop" not in masked


def test_masked_api_key_handles_short_and_empty() -> None:
    assert llm_config.masked_api_key("") == ""
    assert llm_config.masked_api_key("abc") == "***"


def test_effective_aux_model_falls_back_to_model() -> None:
    cfg = llm_config.LlmConfig(base_url="u", api_key="k", model="main", aux_model="")
    assert cfg.effective_aux_model == "main"
    cfg2 = llm_config.LlmConfig(base_url="u", api_key="k", model="main", aux_model="aux")
    assert cfg2.effective_aux_model == "aux"
