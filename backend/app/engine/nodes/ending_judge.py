"""步骤 5.6：结局类型规则判定（基于 evaluate_state 输出的 confession_response 语义标签）+ 从 ending_judge_prompt.md 读模板生成评价。"""

from __future__ import annotations

import logging
from typing import Any, cast

from app.engine.llm_client import call_llm, get_auxiliary_model
from app.engine.prompt_template import apply_template_placeholders, state_to_replacement_map
from app.engine.prompts.loader import read_prompt
from app.engine.state import ConversationState, HiddenState

logger = logging.getLogger(__name__)


def classify_ending_result(heartbeat: float, hidden: HiddenState, stance: str = "ambiguous") -> str:
    """以 evaluate_state 输出的 confession_response 语义标签为主，隐藏状态做合理性兜底。

    stance 取值：accept / reject / delay / ambiguous
    """
    comfort = float(hidden["comfort"])
    trust = float(hidden["trust"])
    alertness = float(hidden["alertness"])

    if stance == "accept":
        if alertness >= 70 or trust < 40 or comfort < 40:
            return "NE"
        return "HE"
    if stance == "reject":
        if alertness >= 70 or heartbeat < 35:
            return "BE"
        return "NE"
    if stance == "delay":
        return "NE"

    # ambiguous 或未知值：退回隐藏状态兜底
    if alertness >= 70 or heartbeat < 35:
        return "BE"
    return "NE"


def ending_judge(state: ConversationState) -> dict[str, Any]:
    """仅在意图为表白/角色表白时由图调度；写 ending_result 与 ending_evaluation。"""
    hb = float(state["new_heartbeat_score"])
    hidden = state["new_hidden_state"]
    ending_result = classify_ending_result(hb, hidden, state.get("confession_response", "ambiguous"))

    merged: dict[str, Any] = dict(state)
    merged["ending_result"] = ending_result
    template = read_prompt("ending_judge_prompt.md")
    user_content = apply_template_placeholders(template, state_to_replacement_map(cast(ConversationState, merged)))

    if not user_content.strip():
        logger.warning("ending_judge: empty template after read/replace, skip LLM")
        return {
            "ending_result": ending_result,
            "ending_evaluation": "（评价暂缺）",
        }

    raw = call_llm(
        [{"role": "user", "content": user_content}],
        temperature=0.5,
        stream=False,
        model=get_auxiliary_model(),
        use_auxiliary_credentials=True,
    )
    assert isinstance(raw, str)
    text = raw.strip()
    if not text:
        logger.warning("ending_judge: LLM returned empty evaluation")
        text = "（评价暂缺）"

    # 第二次 LLM 调用：用户行为复盘
    user_review: str | None = None
    try:
        review_template = read_prompt("user_review_prompt.md")
        review_content = apply_template_placeholders(review_template, state_to_replacement_map(cast(ConversationState, merged)))
        if review_content.strip():
            raw_review = call_llm(
                [{"role": "user", "content": review_content}],
                temperature=0.5,
                stream=False,
                model=get_auxiliary_model(),
                use_auxiliary_credentials=True,
            )
            assert isinstance(raw_review, str)
            user_review = raw_review.strip() or None
        else:
            logger.warning("ending_judge: empty user_review template after replace, skip")
    except Exception:
        logger.exception("ending_judge: failed to generate user_review, continuing without it")

    return {
        "ending_result": ending_result,
        "ending_evaluation": text,
        "user_review": user_review,
    }
