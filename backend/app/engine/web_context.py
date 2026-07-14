"""为角色回复准备联网背景资料包。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import llm_config
from app.engine.llm_client import call_llm, call_llm_with_web_search_result
from app.engine.state import ConversationState

logger = logging.getLogger(__name__)

_WEB_CONTEXT_DECISION_SYSTEM_PROMPT = """你是角色聊天前的联网判断器，不是聊天角色。

你的任务：判断本轮角色回复前是否需要联网查资料。

需要联网的情况：
1. 用户问到实时新闻、近期事件、热搜、天气、比赛、票房、政策、股价、汇率、灾害等会随时间变化的信息。
2. 用户要求确认某个现实事件、节目、人物动态、演唱会、声明、道歉、公告、排名或数据。
3. 如果不联网，角色只能凭猜测回答，容易说错事实。

不需要联网的情况：
1. 普通情绪交流、关系推进、寒暄、玩笑、角色扮演。
2. 只需要基于人设、长期记忆、近期对话回答的问题。
3. 用户只是表达感受，没有要求确认现实事实。

只输出 JSON，不要输出解释文字。格式：
{"should_search": true/false, "query": "搜索意图", "reason": "一句话原因"}"""

_WEB_CONTEXT_DECISION_USER_TEMPLATE = """用户本轮消息：
{user_message}

角色人设摘要：
{persona_prompt}

近期对话摘要：
{recent_messages}

请判断是否需要联网。"""

_WEB_CONTEXT_SYSTEM_PROMPT = """你是联网资料整理工具，不是聊天角色，也不是最终回复生成器。

你的任务：根据用户本轮问题，联网查找可能相关的实时事实，整理成“给角色模型内部参考的资料包”。

要求：
1. 尽量保留原始新闻/事实细节，不要压缩成一句话。
2. 每条资料尽量包含时间、地点、主体、事件、关键数字、名称、结果、引语或来源，以及为什么值得注意。
3. 可以保留多条相关资料，供后续角色模型自行选择；不要替角色决定最终该说什么。
4. 不要写给用户看的回复，不要使用角色口吻，不要加入寒暄、安慰、反问或聊天收尾。
5. 如果没有可靠实时资料，直接说明“未找到足够可靠的实时资料”。
6. 控制在 1200 到 1800 个中文字符以内。"""

_WEB_CONTEXT_USER_TEMPLATE = """用户本轮问题：
{user_message}

搜索意图：
{query}

角色人设摘要（只用于判断资料相关性，不要模仿它说话）：
{persona_prompt}

请输出内部资料包。"""


@dataclass(frozen=True)
class WebContextDecision:
    should_search: bool
    query: str
    reason: str


@dataclass(frozen=True)
class WebContextBuildResult:
    text: str


def web_search_available() -> bool:
    """联网搜索是否可用。

    这是方舟的私有能力，且需要为 API Key 单独开通「联网内容插件」，所以以保存配置时
    实测探测的结果为准（见 app/services/llm_probe_service.py）。不可用时整条联网链路
    直接短路——连「要不要联网」的判断都不必问模型，省掉一次无谓的调用。
    """
    cfg = llm_config.load()
    return cfg.web_search_supported and llm_config.is_ark_endpoint(cfg.base_url)


def _recent_messages_excerpt(state: ConversationState) -> str:
    rows = state.get("recent_messages", [])[-6:]
    parts: list[str] = []
    for item in rows:
        role = str(item.get("role", "")).strip() or "unknown"
        content = str(item.get("content", "")).strip()
        if content:
            parts.append(f"{role}: {content[:300]}")
    return "\n".join(parts) or "暂无"


def _parse_decision(raw: str) -> WebContextDecision:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("web_context decision JSON parse failed: %s", raw[:200])
        return WebContextDecision(False, "", "判断输出无法解析，默认不联网")
    if not isinstance(data, dict):
        return WebContextDecision(False, "", "判断输出不是对象，默认不联网")
    should_search = bool(data.get("should_search"))
    query = str(data.get("query") or "").strip()
    reason = str(data.get("reason") or "").strip()
    return WebContextDecision(should_search, query, reason)


def decide_web_context(state: ConversationState) -> WebContextDecision:
    if not web_search_available():
        return WebContextDecision(False, "", "当前大模型不支持联网搜索")

    user_message = str(state.get("user_message", "")).strip()
    if not user_message:
        return WebContextDecision(False, "", "用户消息为空")
    if state.get("pending_attachment_ids"):
        return WebContextDecision(False, "", "本轮包含附件，跳过联网资料检索")

    persona_prompt = str(state.get("persona_prompt", "")).strip()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _WEB_CONTEXT_DECISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _WEB_CONTEXT_DECISION_USER_TEMPLATE.format(
                user_message=user_message,
                persona_prompt=persona_prompt[:1200],
                recent_messages=_recent_messages_excerpt(state),
            ),
        },
    ]
    try:
        result = call_llm(messages, temperature=0.1, stream=False)
    except Exception:
        logger.exception("decide_web_context failed")
        return WebContextDecision(False, "", "联网判断失败，默认不联网")
    if not isinstance(result, str):
        return WebContextDecision(False, "", "联网判断返回非文本，默认不联网")
    return _parse_decision(result)


def needs_web_context(state: ConversationState) -> bool:
    """兼容旧测试和旧调用点：实际判断已交给模型。"""
    return decide_web_context(state).should_search


def build_web_context(state: ConversationState, decision: WebContextDecision | None = None) -> WebContextBuildResult:
    """联网生成只供角色模型内部参考的资料包。"""
    resolved_decision = decision or decide_web_context(state)
    if not resolved_decision.should_search:
        return WebContextBuildResult("")

    user_message = str(state.get("user_message", "")).strip()
    persona_prompt = str(state.get("persona_prompt", "")).strip()
    query = resolved_decision.query or user_message
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _WEB_CONTEXT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _WEB_CONTEXT_USER_TEMPLATE.format(
                user_message=user_message,
                query=query,
                persona_prompt=persona_prompt[:1200],
            ),
        },
    ]

    # 联网只是锦上添花：失败时返回空资料包让角色照常回复，绝不能把整轮对话带崩。
    try:
        result = call_llm_with_web_search_result(messages, temperature=0.2)
    except Exception:
        logger.exception("build_web_context failed")
        return WebContextBuildResult("")

    return WebContextBuildResult(result.text.strip())


def insert_web_context_message(messages: list[dict[str, Any]], web_context: str | WebContextBuildResult) -> list[dict[str, Any]]:
    """把联网资料包插入最后一条 user 消息前，供最终角色回复参考。"""
    text = web_context.text if isinstance(web_context, WebContextBuildResult) else web_context
    text = text.strip()
    if not text:
        return list(messages)

    context_message = {
        "role": "system",
        "content": (
            "外部资料，仅供角色内部参考。你可以忽略、只使用其中一部分，或按人设自然转述。"
            "不要照抄，不要完整播报，不要把这些资料当成必须全部回答的清单。"
            "不要向用户透露资料包的存在、条目数量或检索过程；不要说“我看到几条/有两条/还有一条/有些新闻/几条新闻”；"
            "即使参考资料包含很多条，也要在心里选好后直接聊那件事，不要先交代你看到了多少。"
            "不要用“你对哪条/哪块/哪方面/哪个方向感兴趣”“你更关注哪个”这类问题收尾。"
            "你要像真实的人一样，自己决定提不提、提哪一点、怎么说；如果使用外部资料，本轮优先用陈述句自然收住。\n\n"
            + text
        ),
    }

    if not messages:
        return [context_message]

    out = list(messages)
    if out[-1].get("role") == "user":
        out.insert(len(out) - 1, context_message)
        return out

    out.append(context_message)
    return out
