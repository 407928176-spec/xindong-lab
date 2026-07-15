"""大模型连通性探测：验证用户填的配置能不能用，并测出是否支持联网搜索。

被 ``POST /api/config/llm/test``（只测不存）和 ``PUT /api/config/llm``（存之前先测）
调用。这里的核心价值是**把各家厂商的报错翻译成人话**——普通玩家看到
``AuthenticationError: Error code: 401`` 是不知道该改哪一栏的。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from urllib.parse import urlparse

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
    # 实测可用的 Base URL。可能与用户填的不同——见 probe() 里的 /v1 自动补全。
    base_url: str = ""


@dataclass(frozen=True)
class _Attempt:
    """一次「用某个 Base URL 实测」的结果。"""

    ok: bool
    message: str
    # 这类失败是否可能只是地址缺了 /v1，值得补上再试一次。
    may_need_v1: bool = False


def _with_v1_suffix(base_url: str) -> str:
    """返回补上 /v1 的地址；已经带版本段（v1 / v3 …）时返回空串表示不必再试。"""
    url = base_url.strip().rstrip("/")
    if not url:
        return ""
    path = (urlparse(url).path or "").strip("/")
    # 方舟是 /api/v3、通义是 /compatible-mode/v1 —— 已经带版本段的一律不动，
    # 免得把本来对的地址拼成 /api/v3/v1 这种更糟的东西。
    if path and re.fullmatch(r"v\d+", path.split("/")[-1]):
        return ""
    return f"{url}/v1"


def _looks_like_chat_completion(completion: object) -> bool:
    """判断返回的是不是一个真正的对话补全响应。

    这条检查是必需的：如果 Base URL 少了 /v1 之类的路径，请求会打到供应商的**网站首页**，
    拿回一个 HTTP 200 的 HTML 页面。openai SDK 遇到非 JSON 响应不会抛异常，而是把原始正文
    原样返回（一个 str）。此时「没报错」根本不等于「能用」——玩家会带着一份看似通过、
    实则用不了的配置进游戏，然后在人设创建或聊天时撞上「模型返回为空」。
    """
    return bool(getattr(completion, "choices", None))


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


def _make_client(cfg: LlmConfig) -> OpenAI:
    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=_PROBE_TIMEOUT, max_retries=0)


def _attempt(cfg: LlmConfig) -> _Attempt:
    """用 cfg 里的 Base URL 实测一次主模型（必要时再测辅助模型）。"""
    client = _make_client(cfg)

    # 最小请求验证「Key + Base URL + 模型名」三件套。方舟需要额外的 thinking 参数，
    # 别家收到未知字段会 400，所以这里必须条件化。
    extra_body = {"thinking": {"type": "disabled"}} if is_ark_endpoint(cfg.base_url) else {}
    try:
        completion = client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            extra_body=extra_body,
        )
    except openai.NotFoundError as err:
        # 404 可能是模型名不对，也可能是接口路径不对（缺 /v1）。后者补上就能好，值得再试一次。
        return _Attempt(False, _translate_error(err, cfg), may_need_v1=True)
    except Exception as err:
        logger.info("LLM 连通性探测失败: %s", type(err).__name__)
        return _Attempt(False, _translate_error(err, cfg))

    # 没抛异常 ≠ 能用：地址不对时供应商可能回一个 200 的网页，SDK 会原样返回正文。
    # 必须在这里拦住，否则玩家会存下一份「测试通过、进游戏就崩」的配置。
    if not _looks_like_chat_completion(completion):
        logger.info("LLM 探测返回了非对话补全响应: %s", type(completion).__name__)
        return _Attempt(
            False,
            f"Base URL「{cfg.base_url}」没有返回模型接口应有的响应（更像是一个网页）。"
            "请检查地址是否填对——大多数供应商需要以 /v1 结尾。",
            may_need_v1=True,
        )

    # 辅助模型如果单独指定了，也要验一遍——否则用户要等到第一次触发状态评估才发现填错。
    aux = cfg.effective_aux_model
    if aux and aux != cfg.model:
        aux_cfg = LlmConfig(base_url=cfg.base_url, api_key=cfg.api_key, model=aux)
        try:
            aux_completion = client.chat.completions.create(
                model=aux,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                extra_body=extra_body,
            )
        except Exception as err:
            logger.info("辅助模型探测失败: %s", type(err).__name__)
            return _Attempt(False, "辅助模型有问题：" + _translate_error(err, aux_cfg))
        if not _looks_like_chat_completion(aux_completion):
            return _Attempt(False, f"辅助模型「{aux}」没有返回模型接口应有的响应。")

    return _Attempt(True, "连接成功，模型可以正常使用。")


def _success(cfg: LlmConfig, message: str) -> ProbeResult:
    supported, ws_msg = _probe_web_search(cfg, _make_client(cfg))
    return ProbeResult(
        ok=True,
        message=message,
        web_search_supported=supported,
        web_search_message=ws_msg,
        base_url=cfg.base_url,
    )


def probe(cfg: LlmConfig) -> ProbeResult:
    """实测一份配置：先验主模型能不能调通，再测联网能力。

    Base URL 缺 /v1 是最常见的填法问题：OpenAI SDK 要求 Base URL 自带 /v1（它只往后拼
    ``/chat/completions``），而 Anthropic 系 SDK 会自己补 /v1。玩家从 Claude 类工具里把
    地址原样搬过来，就会打到供应商的首页上。这里不靠猜——补上 /v1 实测一次，真能通才改用它。
    """
    if not cfg.is_complete:
        return ProbeResult(False, "Base URL、API Key、模型名都要填。", base_url=cfg.base_url)

    first = _attempt(cfg)
    if first.ok:
        return _success(cfg, first.message)

    if first.may_need_v1:
        candidate = _with_v1_suffix(cfg.base_url)
        if candidate:
            retry_cfg = replace(cfg, base_url=candidate)
            second = _attempt(retry_cfg)
            if second.ok:
                logger.info("Base URL 自动补全 /v1 后探测通过")
                return _success(
                    retry_cfg,
                    f"连接成功。你填的「{cfg.base_url}」不是可用的接口地址，"
                    f"已自动更正为「{candidate}」。",
                )
            # 补上 /v1 后报的不再是「像个网页」，说明地址这下是对的，问题另有其人
            # （Key、模型名…）。报这个更接近真相的错误，免得玩家先被地址带偏、
            # 改完地址才发现真正的错在别处，白跑一轮。
            if not second.may_need_v1:
                return ProbeResult(
                    False,
                    f"{second.message}（注：你填的 Base URL 缺少 /v1，测试时已按「{candidate}」访问）",
                    base_url=cfg.base_url,
                )

    return ProbeResult(False, first.message, base_url=cfg.base_url)
