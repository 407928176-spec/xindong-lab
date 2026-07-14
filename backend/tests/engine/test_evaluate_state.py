from __future__ import annotations

import json
from unittest.mock import patch

from app.engine import prompt_template
from app.engine.nodes import evaluate_state as evaluate_state_module
from app.engine.state import minimal_conversation_state


def test_state_to_replacement_map_and_apply_placeholders() -> None:
    state = minimal_conversation_state()
    state["character_reply"] = "角色说"
    state["user_message"] = "用户说"
    repl = prompt_template.state_to_replacement_map(state)
    assert "character_reply" in repl and repl["character_reply"] == "角色说"
    tpl = "U={user_message}|R={character_reply}|X={nonexistent}"
    filled = prompt_template.apply_template_placeholders(tpl, repl)
    assert filled == "U=用户说|R=角色说|X="


def test_apply_placeholders_hidden_state_json_shape() -> None:
    state = minimal_conversation_state()
    repl = prompt_template.state_to_replacement_map(state)
    assert '"comfort"' in repl["hidden_state"]


def test_compute_heartbeat_score_all_mid() -> None:
    hs = {
        "comfort": 50.0,
        "interest": 50.0,
        "trust": 50.0,
        "alertness": 50.0,
        "baseline_compatibility": 50.0,
    }
    assert evaluate_state_module.compute_heartbeat_score(hs) == 50.0


def test_compute_heartbeat_score_liked_state_above_mid() -> None:
    hs = {
        "comfort": 70.0,
        "interest": 75.0,
        "trust": 60.0,
        "alertness": 30.0,
        "baseline_compatibility": 75.0,
    }
    assert evaluate_state_module.compute_heartbeat_score(hs) == 72.25


def test_compute_heartbeat_score_guarded_state_below_mid() -> None:
    hs = {
        "comfort": 35.0,
        "interest": 40.0,
        "trust": 35.0,
        "alertness": 75.0,
        "baseline_compatibility": 40.0,
    }
    assert evaluate_state_module.compute_heartbeat_score(hs) == 33.5


def test_parse_evaluation_llm_output_strips_json_fence() -> None:
    inner = {
        "intent": "表白",
        "confession_response": "accept",
        "state_changes": {
            "comfort_delta": 1,
            "interest_delta": 0,
            "trust_delta": 0,
            "alertness_delta": 0,
            "reason": "ok",
        },
    }
    raw = "```json\n" + json.dumps(inner, ensure_ascii=False) + "\n```"
    intent, sc, stance, ok = evaluate_state_module.parse_evaluation_llm_output(raw)
    assert ok
    assert intent == "表白"
    assert sc["comfort_delta"] == 1.0
    assert sc["reason"] == "ok"
    assert stance == "accept"


def test_parse_evaluation_llm_output_invalid_json_defaults() -> None:
    intent, sc, stance, ok = evaluate_state_module.parse_evaluation_llm_output("not json {{{")
    assert not ok
    assert intent == "闲聊"
    assert sc["comfort_delta"] == 0.0
    assert stance == "ambiguous"


def test_parse_clamps_extreme_deltas() -> None:
    raw = json.dumps(
        {
            "intent": "闲聊",
            "confession_response": "ambiguous",
            "state_changes": {
                "comfort_delta": 99,
                "interest_delta": -99,
                "trust_delta": 0,
                "alertness_delta": 0,
                "reason": "",
            },
        },
        ensure_ascii=False,
    )
    _intent, sc, _stance, ok = evaluate_state_module.parse_evaluation_llm_output(raw)
    assert ok
    assert sc["comfort_delta"] == 10.0
    assert sc["interest_delta"] == -10.0


def test_parse_confession_response_unknown_value_defaults_to_ambiguous() -> None:
    raw = json.dumps(
        {
            "intent": "表白",
            "confession_response": "maybe",
            "state_changes": {"comfort_delta": 0, "interest_delta": 0, "trust_delta": 0, "alertness_delta": 0, "reason": ""},
        },
        ensure_ascii=False,
    )
    _intent, _sc, stance, ok = evaluate_state_module.parse_evaluation_llm_output(raw)
    assert ok
    assert stance == "ambiguous"


def test_parse_confession_response_missing_defaults_to_ambiguous() -> None:
    raw = json.dumps(
        {
            "intent": "闲聊",
            "state_changes": {"comfort_delta": 0, "interest_delta": 0, "trust_delta": 0, "alertness_delta": 0, "reason": ""},
        },
        ensure_ascii=False,
    )
    _intent, _sc, stance, _ok = evaluate_state_module.parse_evaluation_llm_output(raw)
    assert stance == "ambiguous"


def test_evaluate_state_mock_positive_deltas_and_heartbeat() -> None:
    state = minimal_conversation_state()
    state["character_reply"] = "谢谢"
    llm_payload = {
        "intent": "关心",
        "confession_response": "ambiguous",
        "state_changes": {
            "comfort_delta": 5,
            "interest_delta": 3,
            "trust_delta": 4,
            "alertness_delta": -1,
            "reason": "正面",
        },
    }
    with patch.object(evaluate_state_module, "read_prompt", return_value="{character_reply}"):
        with patch.object(evaluate_state_module, "call_llm", return_value=json.dumps(llm_payload, ensure_ascii=False)) as m:
            out = evaluate_state_module.evaluate_state(state)
    m.assert_called_once()
    assert out["intent"] == "关心"
    assert out["confession_response"] == "ambiguous"
    assert out["state_changes"]["comfort_delta"] == 5.0
    new_hs = out["new_hidden_state"]
    assert new_hs["comfort"] == 55.0
    assert new_hs["baseline_compatibility"] == 50.0
    expected_hb = evaluate_state_module.compute_heartbeat_score(new_hs)
    assert out["new_heartbeat_score"] == expected_hb


def test_evaluate_state_mock_offensive_directions() -> None:
    state = minimal_conversation_state()
    llm_payload = {
        "intent": "冒犯",
        "confession_response": "ambiguous",
        "state_changes": {
            "comfort_delta": -5,
            "interest_delta": -4,
            "trust_delta": -3,
            "alertness_delta": 8,
            "reason": "冲突",
        },
    }
    with patch.object(evaluate_state_module, "read_prompt", return_value="x"):
        with patch.object(evaluate_state_module, "call_llm", return_value=json.dumps(llm_payload, ensure_ascii=False)):
            out = evaluate_state_module.evaluate_state(state)
    assert out["state_changes"]["alertness_delta"] == 8.0
    assert out["new_hidden_state"]["alertness"] > state["hidden_state"]["alertness"]
    assert out["new_hidden_state"]["comfort"] < state["hidden_state"]["comfort"]


def test_evaluate_state_confession_intent_with_acceptance() -> None:
    state = minimal_conversation_state()
    with patch.object(evaluate_state_module, "read_prompt", return_value="x"):
        with patch.object(
            evaluate_state_module,
            "call_llm",
            return_value='{"intent":"表白","confession_response":"accept","state_changes":{"comfort_delta":0,"interest_delta":0,"trust_delta":0,"alertness_delta":0,"reason":""}}',
        ):
            out = evaluate_state_module.evaluate_state(state)
    assert out["intent"] == "表白"
    assert out["confession_response"] == "accept"


def test_evaluate_state_empty_template_skips_llm() -> None:
    state = minimal_conversation_state()
    with patch.object(evaluate_state_module, "read_prompt", return_value="   \n  "):
        with patch.object(evaluate_state_module, "call_llm", return_value="should_not_use") as m:
            out = evaluate_state_module.evaluate_state(state)
    m.assert_not_called()
    assert out["intent"] == "闲聊"
    assert out["state_changes"]["comfort_delta"] == 0.0
    assert out["confession_response"] == "ambiguous"
