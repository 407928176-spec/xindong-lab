"""大模型连通性探测：验证用户填的配置能不能用，并测出是否支持联网搜索。

被 ``POST /api/config/llm/test``（只测不存）和 ``PUT /api/config/llm``（存之前先测）
调用。这里的核心价值是**把各家厂商的报错翻译成人话**——普通玩家看到
``AuthenticationError: Error code: 401`` 是不知道该改哪一栏的。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import openai
from openai import OpenAI

from app.config.llm_config import LlmConfig, is_ark_endpoint

logger = logging.getLogger(__name__)

# 探测请求的超时（秒）。填错 Base URL 时不能让用户在向导里干等太久。
_PROBE_TIMEOUT = 30.0


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str
    web_search_supported: bool = False
    web_search_message: str = ""


def _translate_error(err: Exception, cfg: LlmConfig) -> str:
    """把 openai SDK 的异常翻成「该改哪一栏」。"""
    if isinstance(err, openai.AuthenticationError):
        return "API Key 无效或已过期，请检查 API Key 是否填对、是否已开通对应模型的权限。"
    if isinstance(err, openai.PermissionDeniedError):
        return (
            f"API Key 没有访问模型「{cfg.model}」的权限。"
            "请到供应商控制台确认该 Key 已开通这个模型，或换一个模型名。"
        )
    if isinstance(err, openai.NotFoundError):
        return (
            f"找不到模型「{cfg.model}」。请检查模型名是否拼写正确"
            "（注意有些供应商要求填模型 ID 而不是展示名称），也确认 Base URL 是否填对。"
        )
    if isinstance(err, openai.RateLimitError):
        return "请求被限流，或账户余额 / 配额不足。请稍后重试，或到供应商控制台检查余额。"
    if isinstance(err, openai.APIConnectionError):
        return (
            f"连不上 Base URL「{cfg.base_url}」。请检查地址是否填对"
            "（大多数供应商需要以 /v1 结尾）、本机网络是否正常、是否需要代理。"
        )
    if isinstance(err, openai.BadRequestError):
        return f"供应商拒绝了请求：{str(err)[:200]}。通常是模型名不对，或该模型不支持对话补全接口。"
    if isinstance(err, openai.APIStatusError):
        return f"供应商返回错误（HTTP {err.status_code}）：{str(err)[:200]}"
    return f"连接失败：{type(err).__name__}: {str(err)[:200]}"


def _probe_web_search(cfg: LlmConfig, client: OpenAI) -> tuple[bool, str]:
    """探测联网搜索能力。

    联网搜索是火山方舟的私有能力（``/responses`` 端点 + 内置 ``web_search`` 工具），
    OpenAI 标准接口没有对应物。所以非方舟端点直接判定不支持，不浪费一次调用；
    方舟端点则实打实发一个最小请求——因为方舟还要求这个 Key 在控制台单独开通
    「联网内容插件」，光看 URL 判断不出来。
    """
    if not is_ark_endpoint(cfg.base_url):
        return False, "当前供应商不是火山方舟，不支持联网搜索。角色将无法获取实时信息，其余玩法不受影响。"

    try:
        client.responses.create(
            model=cfg.model,
            input=[{"role": "user", "content": "hi"}],
            tools=[{"type": "web_search", "sources": ["toutiao", "douyin", "moji"]}],  # type: ignore[list-item]
            max_output_tokens=16,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return True, "联网搜索可用，角色可以聊实时话题（天气、新闻等）。"
    except Exception as err:
        logger.info("web_search 探测未通过: %s", type(err).__name__)
        return False, (
            "这个方舟模型 / API Key 暂时用不了联网搜索。"
            "请到方舟控制台为该 API Key 开通「联网内容插件」，并确认模型支持 Responses API。"
            "不影响正常聊天。"
        )


def probe(cfg: LlmConfig) -> ProbeResult:
    """实测一份配置：先验主模型能不能调通，再测联网能力。"""
    if not cfg.is_complete:
        return ProbeResult(False, "Base URL、API Key、模型名都要填。")

    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=_PROBE_TIMEOUT, max_retries=0)

    # 最小请求验证「Key + Base URL + 模型名」三件套。方舟需要额外的 thinking 参数，
    # 别家收到未知字段会 400，所以这里必须条件化。
    extra_body = {"thinking": {"type": "disabled"}} if is_ark_endpoint(cfg.base_url) else {}
    try:
        client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            extra_body=extra_body,
        )
    except Exception as err:
        logger.info("LLM 连通性探测失败: %s", type(err).__name__)
        return ProbeResult(False, _translate_error(err, cfg))

    # 辅助模型如果单独指定了，也要验一遍——否则用户要等到第一次触发状态评估才发现填错。
    aux = cfg.effective_aux_model
    if aux and aux != cfg.model:
        try:
            client.chat.completions.create(
                model=aux,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                extra_body=extra_body,
            )
        except Exception as err:
            logger.info("辅助模型探测失败: %s", type(err).__name__)
            aux_cfg = LlmConfig(base_url=cfg.base_url, api_key=cfg.api_key, model=aux)
            return ProbeResult(False, "辅助模型有问题：" + _translate_error(err, aux_cfg))

    supported, ws_msg = _probe_web_search(cfg, client)
    return ProbeResult(
        ok=True,
        message="连接成功，模型可以正常使用。",
        web_search_supported=supported,
        web_search_message=ws_msg,
    )
