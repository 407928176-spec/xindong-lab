"""OpenAI 兼容大模型接口封装。

**配置来源**：全部来自 :mod:`app.config.llm_config`（网页向导写入的 JSON，或环境变量
覆盖）。本模块不读任何厂商专属环境变量，也绝不在源码里写死 Key。

**兼容性**：只使用 OpenAI 标准的 ``chat/completions``，因此任何 OpenAI 兼容端点
（OpenAI、DeepSeek、火山方舟、通义、Ollama、vLLM、OpenRouter…）都能直接用。

**两处厂商差异**，都通过 :func:`app.config.llm_config.is_ark_endpoint` 判断后条件启用，
不会污染标准端点：

- ``thinking: disabled``：方舟 Seed 系列默认开启深度思考会拖慢回复，需要显式关掉。
  但这是方舟私有字段，发给 OpenAI 官方接口会 400。
- **联网搜索**：走方舟私有的 ``/responses`` 端点 + 内置 ``web_search`` 工具。别家没有
  对应能力，因此 ``use_web_search=True`` 在非方舟端点上会被静默忽略（走普通补全）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, OpenAI
from openai.types.responses import ResponseTextDeltaEvent

from app.config import llm_config

logger = logging.getLogger(__name__)

# 方舟联网搜索的数据源。仅在方舟端点上生效。
WEB_SEARCH_SOURCES = ["toutiao", "douyin", "moji"]
WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search", "sources": WEB_SEARCH_SOURCES}


@dataclass(frozen=True)
class WebSearchLLMResult:
    text: str
    sources: list[dict[str, Any]]
    used_web_search: bool
    fallback_used: bool = False


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------


def _require_config() -> llm_config.LlmConfig:
    cfg = llm_config.load()
    if not cfg.is_complete:
        raise ValueError("尚未配置大模型，请先在网页上完成大模型设置（/setup）。")
    return cfg


def get_api_key() -> str:
    return _require_config().api_key


def get_base_url() -> str:
    return _require_config().base_url


def get_chat_model() -> str:
    """角色回复使用的模型。"""
    return _require_config().model


def get_auxiliary_model() -> str:
    """状态评估 / 终局评价 / 长记忆摘要等辅助链路使用的模型。"""
    return _require_config().effective_aux_model


def get_extract_model() -> str:
    """人设静默抽取 JSON：与辅助链路一致。"""
    return get_auxiliary_model()


def get_summary_model() -> str:
    """长记忆摘要：与辅助链路一致。"""
    return get_auxiliary_model()


def _is_ark() -> bool:
    return llm_config.is_ark_endpoint(llm_config.load().base_url)


def _extra_body() -> dict[str, Any]:
    """方舟需要显式关闭深度思考；标准 OpenAI 端点收到未知字段会 400，所以必须条件化。"""
    return {"thinking": {"type": "disabled"}} if _is_ark() else {}


def _web_search_enabled() -> bool:
    """联网搜索需要同时满足：端点是方舟 + 保存配置时实测探测通过。"""
    cfg = llm_config.load()
    return cfg.web_search_supported and llm_config.is_ark_endpoint(cfg.base_url)


def _web_search_tools() -> list[dict[str, Any]]:
    return [dict(WEB_SEARCH_TOOL, sources=list(WEB_SEARCH_SOURCES))]


# ---------------------------------------------------------------------------
# 客户端构造（按配置缓存，避免每次调用都新建连接池）
# ---------------------------------------------------------------------------

_sync_client: tuple[tuple[str, str], OpenAI] | None = None
_async_client: tuple[tuple[str, str], AsyncOpenAI] | None = None


def create_sync_client() -> OpenAI:
    global _sync_client
    cfg = _require_config()
    key = (cfg.base_url, cfg.api_key)
    if _sync_client is None or _sync_client[0] != key:
        _sync_client = (key, OpenAI(api_key=cfg.api_key, base_url=cfg.base_url))
    return _sync_client[1]


def create_async_client() -> AsyncOpenAI:
    global _async_client
    cfg = _require_config()
    key = (cfg.base_url, cfg.api_key)
    if _async_client is None or _async_client[0] != key:
        _async_client = (key, AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url))
    return _async_client[1]


def reset_clients() -> None:
    """配置变更后丢弃缓存的客户端（由 config 路由在保存后调用）。"""
    global _sync_client, _async_client
    _sync_client = None
    _async_client = None


def _resolve_model(model: str | None, use_auxiliary_credentials: bool) -> str:
    resolved = (model or "").strip()
    if resolved:
        return resolved
    return get_auxiliary_model() if use_auxiliary_credentials else get_chat_model()


# ---------------------------------------------------------------------------
# Responses API（仅方舟：联网搜索）
# ---------------------------------------------------------------------------


def _as_plain_data(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _as_plain_data(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_as_plain_data(v) for v in value]
    if hasattr(value, "model_dump"):
        return _as_plain_data(value.model_dump())
    if hasattr(value, "dict"):
        return _as_plain_data(value.dict())
    return str(value)


def _extract_web_search_sources(value: Any) -> list[dict[str, Any]]:
    plain = _as_plain_data(value)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            keys = set(item.keys())
            if {"url", "title"} & keys or {"source", "site", "domain"} & keys:
                candidate = {
                    k: item[k]
                    for k in (
                        "title",
                        "url",
                        "source",
                        "site",
                        "domain",
                        "publish_time",
                        "published_at",
                        "date",
                        "snippet",
                        "summary",
                    )
                    if k in item and item[k]
                }
                if candidate:
                    marker = str(candidate)
                    if marker not in seen:
                        found.append(candidate)
                        seen.add(marker)
            for v in item.values():
                visit(v)
            return
        if isinstance(item, list):
            for v in item:
                visit(v)

    visit(plain)
    return found[:20]


def _split_messages_for_responses(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """把 messages 拆成 Responses API 的 instructions（system）与 input（其余）。"""
    instructions: str | None = None
    input_msgs: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content", "")
            instructions = content if isinstance(content, str) else str(content)
        else:
            input_msgs.append(m)
    return instructions, input_msgs


def _call_via_responses(
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    stream: bool,
    resolved_model: str,
    client: OpenAI,
) -> "str | Iterator[str]":
    """方舟 Responses API（启用内置 web_search）。失败时抛出，由调用方回退。"""
    instructions, input_msgs = _split_messages_for_responses(messages)

    if not stream:
        response = client.responses.create(
            model=resolved_model,
            input=input_msgs,  # type: ignore[arg-type]
            instructions=instructions,
            tools=_web_search_tools(),  # type: ignore[list-item]
            temperature=temperature,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return (response.output_text or "").strip()

    def _gen() -> "Iterator[str]":
        s = client.responses.create(
            model=resolved_model,
            input=input_msgs,  # type: ignore[arg-type]
            instructions=instructions,
            tools=_web_search_tools(),  # type: ignore[list-item]
            temperature=temperature,
            stream=True,
            extra_body={"thinking": {"type": "disabled"}},
        )
        for event in s:
            if isinstance(event, ResponseTextDeltaEvent) and event.delta:
                yield event.delta

    return _gen()


async def _acall_via_responses(
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    stream: bool,
    resolved_model: str,
    client: AsyncOpenAI,
) -> "str | AsyncIterator[str]":
    """异步版 Responses API 调用。失败时抛出，由调用方回退。"""
    instructions, input_msgs = _split_messages_for_responses(messages)

    if not stream:
        response = await client.responses.create(
            model=resolved_model,
            input=input_msgs,  # type: ignore[arg-type]
            instructions=instructions,
            tools=_web_search_tools(),  # type: ignore[list-item]
            temperature=temperature,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return (response.output_text or "").strip()

    async def _agen() -> "AsyncIterator[str]":
        s = await client.responses.create(
            model=resolved_model,
            input=input_msgs,  # type: ignore[arg-type]
            instructions=instructions,
            tools=_web_search_tools(),  # type: ignore[list-item]
            temperature=temperature,
            stream=True,
            extra_body={"thinking": {"type": "disabled"}},
        )
        async for event in s:
            if isinstance(event, ResponseTextDeltaEvent) and event.delta:
                yield event.delta

    return _agen()


def call_llm_with_web_search_result(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    model: str | None = None,
    use_auxiliary_credentials: bool = False,
) -> WebSearchLLMResult:
    """带联网搜索的调用，并回传引用来源。不支持联网时直接走普通补全。"""
    client = create_sync_client()
    resolved = _resolve_model(model, use_auxiliary_credentials)

    if _web_search_enabled():
        try:
            instructions, input_msgs = _split_messages_for_responses(messages)
            response = client.responses.create(
                model=resolved,
                input=input_msgs,  # type: ignore[arg-type]
                instructions=instructions,
                tools=_web_search_tools(),  # type: ignore[list-item]
                temperature=temperature,
                extra_body={"thinking": {"type": "disabled"}},
            )
            return WebSearchLLMResult(
                text=(response.output_text or "").strip(),
                sources=_extract_web_search_sources(response),
                used_web_search=True,
                fallback_used=False,
            )
        except Exception as err:
            logger.warning("Responses API 调用失败，回退到 chat/completions（无联网搜索）: %s", err)

    completion = client.chat.completions.create(
        model=resolved,
        messages=messages,
        temperature=temperature,
        extra_body=_extra_body(),
    )
    content = completion.choices[0].message.content
    return WebSearchLLMResult(
        text=(content or "").strip(),
        sources=[],
        used_web_search=False,
        fallback_used=True,
    )


# ---------------------------------------------------------------------------
# 主调用入口
# ---------------------------------------------------------------------------


def call_llm(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.8,
    stream: bool = False,
    model: str | None = None,
    use_auxiliary_credentials: bool = False,
    use_web_search: bool = False,
) -> str | Iterator[str]:
    """同步调用聊天补全。

    - ``use_auxiliary_credentials=True``：使用辅助模型（状态评估 / 终局 / 摘要）。
    - ``use_web_search=True``：仅在方舟且探测通过时生效，否则静默走普通补全。
    """
    client = create_sync_client()
    resolved = _resolve_model(model, use_auxiliary_credentials)

    if use_web_search and _web_search_enabled():
        try:
            return _call_via_responses(
                messages,
                temperature=temperature,
                stream=stream,
                resolved_model=resolved,
                client=client,
            )
        except Exception as err:
            logger.warning("Responses API 调用失败，回退到 chat/completions（无联网搜索）: %s", err)

    extra_body = _extra_body()

    if not stream:
        completion = client.chat.completions.create(
            model=resolved,
            messages=messages,
            temperature=temperature,
            extra_body=extra_body,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()

    def _gen() -> Iterator[str]:
        s = client.chat.completions.create(
            model=resolved,
            messages=messages,
            temperature=temperature,
            stream=True,
            extra_body=extra_body,
        )
        for chunk in s:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    return _gen()


async def acall_llm(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.8,
    stream: bool = False,
    model: str | None = None,
    use_auxiliary_credentials: bool = False,
    use_web_search: bool = False,
) -> str | AsyncIterator[str]:
    """异步调用聊天补全。语义与 :func:`call_llm` 一致。"""
    client = create_async_client()
    resolved = _resolve_model(model, use_auxiliary_credentials)

    if use_web_search and _web_search_enabled():
        try:
            return await _acall_via_responses(
                messages,
                temperature=temperature,
                stream=stream,
                resolved_model=resolved,
                client=client,
            )
        except Exception as err:
            logger.warning("Responses API 异步调用失败，回退到 chat/completions（无联网搜索）: %s", err)

    extra_body = _extra_body()

    if not stream:
        completion = await client.chat.completions.create(
            model=resolved,
            messages=messages,
            temperature=temperature,
            extra_body=extra_body,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()

    async def _agen() -> AsyncIterator[str]:
        s = await client.chat.completions.create(
            model=resolved,
            messages=messages,
            temperature=temperature,
            stream=True,
            extra_body=extra_body,
        )
        async for chunk in s:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    return _agen()
