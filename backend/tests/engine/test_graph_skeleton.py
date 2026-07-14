from __future__ import annotations

from unittest.mock import patch

from app.engine.graph import build_compiled_graph
from app.engine.nodes import evaluate_state as evaluate_state_module
from app.engine.nodes import generate_reply as generate_reply_module
from app.engine.no_reply import NO_REPLY_TOKEN
from app.engine.state import minimal_conversation_state


def test_graph_skeleton_runs_and_pass_through_preserves_state() -> None:
    app = build_compiled_graph()
    inp = minimal_conversation_state()
    eval_json = (
        '{"intent":"闲聊","state_changes":'
        '{"comfort_delta":0,"interest_delta":0,"trust_delta":0,"alertness_delta":0,"reason":""}}'
    )
    with patch.object(generate_reply_module, "call_llm", return_value=""):
        with patch.object(evaluate_state_module, "call_llm", return_value=eval_json):
            out = app.invoke(inp)
    assert out["character_reply"] == ""
    assert out.get("character_no_reply") is False
    assert out["intent"] == "闲聊"
    assert out["new_heartbeat_score"] == evaluate_state_module.compute_heartbeat_score(
        out["new_hidden_state"]
    )
    assert out["user_message"] == inp["user_message"]


def test_graph_skeleton_exact_no_reply_sets_character_no_reply() -> None:
    app = build_compiled_graph()
    inp = minimal_conversation_state()
    eval_json = (
        '{"intent":"闲聊","state_changes":'
        '{"comfort_delta":0,"interest_delta":0,"trust_delta":0,"alertness_delta":0,"reason":""}}'
    )
    with patch.object(generate_reply_module, "call_llm", return_value=NO_REPLY_TOKEN):
        with patch.object(evaluate_state_module, "call_llm", return_value=eval_json):
            out = app.invoke(inp)
    assert out["character_reply"] == ""
    assert out.get("character_no_reply") is True
