"""步骤 5.4：状态评估——从 evaluate_state_prompt.md 读模板，注入 state 字段，解析 JSON，更新隐藏状态与心动值。"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.engine.llm_client import call_llm, get_auxiliary_model
from app.engine.prompt_template import apply_template_placeholders, state_to_replacement_map
from app.engine.prompts.loader import read_prompt
from app.engine.state import ConversationState, HiddenState, StateChanges

logger = logging.getLogger(__name__)

_DELTA_MIN, _DELTA_MAX = -10.0, 10.0
_HIDDEN_MIN, _HIDDEN_MAX = 0.0, 100.0


def _strip_markdown_code_fence(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if not lines:
        return ""
    # 去掉首行 ``` 或 ```json
    lines = lines[1:]
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_heartbeat_score(hs: HiddenState) -> float:
    """以 50 为中性基线计算心动值，避免中性五维被压到低分段。"""
    hb = (
        50.0
        + (hs["comfort"] - 50.0) * 0.25
        + (hs["interest"] - 50.0) * 0.25
        + (hs["trust"] - 50.0) * 0.30
        - (hs["alertness"] - 50.0) * 0.15
        + (hs["baseline_compatibility"] - 50.0) * 0.20
    )
    return _clamp(hb, _HIDDEN_MIN, _HIDDEN_MAX)


def _empty_state_changes() -> StateChanges:
    return {
        "comfort_delta": 0.0,
        "interest_delta": 0.0,
        "trust_delta": 0.0,
        "alertness_delta": 0.0,
        "reason": "",
    }


def _parse_float_maybe(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return default
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return default
    return default


_VALID_STANCES = {"accept", "reject", "delay", "ambiguous"}


def parse_evaluation_llm_output(raw: str) -> tuple[str, StateChanges, str, bool]:
    """解析评估模型输出。返回 (intent, state_changes, confession_response, parse_ok)。"""
    defaults = ("闲聊", _empty_state_changes(), "ambiguous", False)
    stripped = _strip_markdown_code_fence(raw)
    if not stripped:
        logger.warning("evaluate_state: empty LLM output, using defaults")
        return defaults

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        logger.warning("evaluate_state: JSON parse failed: %s", e)
        return defaults

    if not isinstance(data, dict):
        logger.warning("evaluate_state: root JSON is not object, using defaults")
        return defaults

    intent = data.get("intent", "闲聊")
    if not isinstance(intent, str) or not intent.strip():
        intent = "闲聊"
    else:
        intent = intent.strip()

    raw_stance = data.get("confession_response", "ambiguous")
    confession_response = raw_stance if isinstance(raw_stance, str) and raw_stance in _VALID_STANCES else "ambiguous"

    sc_raw = data.get("state_changes")
    sc = _empty_state_changes()
    if isinstance(sc_raw, dict):
        sc["comfort_delta"] = _clamp(
            _parse_float_maybe(sc_raw.get("comfort_delta"), 0.0),
            _DELTA_MIN,
            _DELTA_MAX,
        )
        sc["interest_delta"] = _clamp(
            _parse_float_maybe(sc_raw.get("interest_delta"), 0.0),
            _DELTA_MIN,
            _DELTA_MAX,
        )
        sc["trust_delta"] = _clamp(
            _parse_float_maybe(sc_raw.get("trust_delta"), 0.0),
            _DELTA_MIN,
            _DELTA_MAX,
        )
        sc["alertness_delta"] = _clamp(
            _parse_float_maybe(sc_raw.get("alertness_delta"), 0.0),
            _DELTA_MIN,
            _DELTA_MAX,
        )
        reason = sc_raw.get("reason", "")
        sc["reason"] = reason.strip() if isinstance(reason, str) else ""

    return intent, sc, confession_response, True


def apply_deltas_to_hidden(prev: HiddenState, deltas: StateChanges) -> HiddenState:
    """四维加 delta 后 clamp；baseline_compatibility 不变。"""
    out: HiddenState = {
        "comfort": _clamp(prev["comfort"] + deltas["comfort_delta"], _HIDDEN_MIN, _HIDDEN_MAX),
        "interest": _clamp(prev["interest"] + deltas["interest_delta"], _HIDDEN_MIN, _HIDDEN_MAX),
        "trust": _clamp(prev["trust"] + deltas["trust_delta"], _HIDDEN_MIN, _HIDDEN_MAX),
        "alertness": _clamp(prev["alertness"] + deltas["alertness_delta"], _HIDDEN_MIN, _HIDDEN_MAX),
        "baseline_compatibility": prev["baseline_compatibility"],
    }
    return out


def evaluate_state(state: ConversationState) -> dict[str, Any]:
    """读取评估模板、调用 LLM、解析 JSON、写入 intent / state_changes / new_hidden_state / new_heartbeat_score。"""
    template = read_prompt("evaluate_state_prompt.md")
    replacements = state_to_replacement_map(state)
    user_content = apply_template_placeholders(template, replacements)

    if not user_content.strip():
        logger.warning("evaluate_state: prompt template empty after read/replace, skip LLM")
        sc = _empty_state_changes()
        new_hs = apply_deltas_to_hidden(state["hidden_state"], sc)
        return {
            "intent": "闲聊",
            "state_changes": sc,
            "new_hidden_state": new_hs,
            "new_heartbeat_score": compute_heartbeat_score(new_hs),
            "confession_response": "ambiguous",
        }

    raw = call_llm(
        [{"role": "user", "content": user_content}],
        temperature=0.3,
        stream=False,
        model=get_auxiliary_model(),
        use_auxiliary_credentials=True,
    )
    assert isinstance(raw, str)
    intent, state_changes, confession_response, _ok = parse_evaluation_llm_output(raw)
    new_hidden_state = apply_deltas_to_hidden(state["hidden_state"], state_changes)
    new_heartbeat_score = compute_heartbeat_score(new_hidden_state)

    return {
        "intent": intent,
        "state_changes": state_changes,
        "new_hidden_state": new_hidden_state,
        "new_heartbeat_score": new_heartbeat_score,
        "confession_response": confession_response,
    }
