"""大模型配置：本项目唯一的 LLM 凭证与模型来源。

设计目标是「下载即玩」：用户不需要编辑任何文件，首次打开网页时由前端向导
（``/setup``）填写 Base URL / API Key / 模型名，经 ``PUT /api/config/llm`` 落到
``backend/data/llm_config.json``。

读取优先级：**环境变量 > JSON 文件**。这样服务器部署或老手可以用环境变量注入而
完全绕过向导，同时普通玩家不用碰命令行。

安全约定：``api_key`` 只在本模块和 ``llm_client`` 内部流转，任何 API 响应都只能
返回 :func:`masked_api_key` 的结果，绝不能把明文 Key 发回前端。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "llm_config.json"


@dataclass(frozen=True)
class LlmConfig:
    """一份完整的大模型配置。

    ``model`` 用于游戏中的角色回复；``aux_model`` 用于状态评估 / 终局文案 / 长记忆
    摘要等辅助链路。两者可以相同——多数用户只会填一个模型名，此时 ``aux_model``
    回落到 ``model``。
    """

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    aux_model: str = ""
    # 是否支持联网搜索。该字段不是用户填的，而是保存配置时由后端实测探测出来的结果，
    # 见 app/services/llm_probe_service.py。
    web_search_supported: bool = False

    @property
    def effective_aux_model(self) -> str:
        """辅助链路实际使用的模型：用户没单独指定时跟随主模型。"""
        return self.aux_model.strip() or self.model.strip()

    @property
    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip() and self.model.strip())


def config_path() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    data_dir = backend_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _CONFIG_FILENAME


# 进程内缓存：LLM 配置在每次调用模型时都要读，不该每次都碰磁盘。
# 由 save() 与 invalidate_cache() 主动失效。
_cached: LlmConfig | None = None


def _read_file_config() -> LlmConfig:
    path = config_path()
    if not path.exists():
        return LlmConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # 配置文件损坏不应该让整个后端起不来：退回空配置，用户会被向导接住重填。
        logger.warning("llm_config.json 读取失败，按未配置处理", exc_info=True)
        return LlmConfig()
    if not isinstance(raw, dict):
        return LlmConfig()
    return LlmConfig(
        base_url=str(raw.get("base_url") or "").strip(),
        api_key=str(raw.get("api_key") or "").strip(),
        model=str(raw.get("model") or "").strip(),
        aux_model=str(raw.get("aux_model") or "").strip(),
        web_search_supported=bool(raw.get("web_search_supported")),
    )


def _apply_env_overrides(cfg: LlmConfig) -> LlmConfig:
    """环境变量逐字段覆盖文件配置（只覆盖非空项，允许混合使用）。"""
    env_base = os.environ.get("LLM_BASE_URL", "").strip()
    env_key = os.environ.get("LLM_API_KEY", "").strip()
    env_model = os.environ.get("LLM_MODEL", "").strip()
    env_aux = os.environ.get("LLM_AUX_MODEL", "").strip()

    out = cfg
    if env_base:
        out = replace(out, base_url=env_base)
    if env_key:
        out = replace(out, api_key=env_key)
    if env_model:
        out = replace(out, model=env_model)
    if env_aux:
        out = replace(out, aux_model=env_aux)

    # 环境变量改了 base_url 却没有探测结果时，用启发式判断兜底：非方舟一定不支持联网，
    # 避免把上一份配置探测出的 True 错误地带到新端点上。
    if env_base and not is_ark_endpoint(out.base_url):
        out = replace(out, web_search_supported=False)
    return out


def load() -> LlmConfig:
    """返回当前生效的配置（带进程内缓存）。"""
    global _cached
    if _cached is None:
        _cached = _apply_env_overrides(_read_file_config())
    return _cached


def invalidate_cache() -> None:
    global _cached
    _cached = None


def save(cfg: LlmConfig) -> LlmConfig:
    """把配置写入 JSON 文件并使缓存失效，返回最终生效的配置。"""
    path = config_path()
    payload = asdict(cfg)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # 配置文件含明文 API Key，收紧到仅属主可读（Windows 上 chmod 基本无效，静默忽略）。
    try:
        path.chmod(0o600)
    except OSError:
        pass
    invalidate_cache()
    return load()


def is_configured() -> bool:
    return load().is_complete


def is_ark_endpoint(base_url: str) -> bool:
    """判断 Base URL 是否指向火山方舟（Volcengine Ark）。

    方舟有两处与 OpenAI 标准不兼容的地方，都依赖这个判断：
    1. 需要额外传 ``extra_body={"thinking": {"type": "disabled"}}`` 关闭深度思考；
       而 OpenAI 官方接口收到未知字段会直接 400。
    2. 联网搜索走方舟私有的 ``/responses`` + ``web_search`` 工具，别家没有。

    只匹配 host，避免 path 或 query 里出现 "ark" 造成误判。
    """
    host = (urlparse(base_url.strip()).hostname or "").lower()
    if not host:
        return False
    return host.endswith("volces.com") or host.startswith("ark.")


def masked_api_key(api_key: str) -> str:
    """脱敏后的 Key，仅用于回显给前端确认「填过了」，绝不返回明文。"""
    k = (api_key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "*" * len(k)
    return f"{k[:4]}{'*' * 8}{k[-4:]}"
