from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import app.engine.graph as graph_module
from app.engine.graph import build_compiled_graph, route_after_evaluation
from app.engine.nodes import ending_judge as ending_judge_module
from app.engine.nodes import evaluate_state as evaluate_state_module
from app.engine.nodes import generate_reply as generate_reply_module
from app.engine.nodes import memory_manager as memory_manager_module
from app.engine.state import minimal_conversation_state


def test_route_after_evaluation_confession_paths() -> None:
    s = minimal_conversation_state()
    s["intent"] = "表白"
    assert route_after_evaluation(s) == "ending_judge"
    s["intent"] = "角色表白"
    assert route_after_evaluation(s) == "ending_judge"
    s["intent"] = "闲聊"
    assert route_after_evaluation(s) == "memory_manager"


def test_invoke_non_confession_calls_memory_manager_not_ending_judge() -> None:
    inp = minimal_conversation_state()
    eval_json = json.dumps(
        {
            "intent": "闲聊",
            "confession_response": "ambiguous",
            "state_changes": {
                "comfort_delta": 0,
                "interest_delta": 0,
                "trust_delta": 0,
                "alertness_delta": 0,
                "reason": "",
            },
        },
        ensure_ascii=False,
    )
    mem = MagicMock(wraps=memory_manager_module.memory_manager)
    end = MagicMock(wraps=ending_judge_module.ending_judge)
    with patch.object(generate_reply_module, "call_llm", return_value=""):
        with patch.object(evaluate_state_module, "call_llm", return_value=eval_json):
            with patch.object(graph_module, "memory_manager", mem):
                with patch.object(graph_module, "ending_judge", end):
                    app = build_compiled_graph()
                    app.invoke(inp)
    mem.assert_called_once()
    end.assert_not_called()


def test_invoke_confession_calls_ending_judge_not_memory_manager() -> None:
    inp = minimal_conversation_state()
    # evaluate_state 从 hidden_state 加 delta 得 new_hidden_state；零 delta 时二者相同，需满足 HE 阈值
    inp["hidden_state"] = {
        "comfort": 95.0,
        "interest": 95.0,
        "trust": 95.0,
        "alertness": 10.0,
        "baseline_compatibility": 50.0,
    }
    inp["new_hidden_state"] = dict(inp["hidden_state"])
    eval_json = json.dumps(
        {
            "intent": "表白",
            "confession_response": "accept",
            "state_changes": {
                "comfort_delta": 0,
                "interest_delta": 0,
                "trust_delta": 0,
                "alertness_delta": 0,
                "reason": "",
            },
        },
        ensure_ascii=False,
    )
    mem = MagicMock(wraps=memory_manager_module.memory_manager)
    end = MagicMock(wraps=ending_judge_module.ending_judge)
    with patch.object(generate_reply_module, "call_llm", return_value="那我们试试吧"):
        with patch.object(evaluate_state_module, "call_llm", return_value=eval_json):
            with patch.object(ending_judge_module, "call_llm", return_value="评价"):
                with patch.object(graph_module, "memory_manager", mem):
                    with patch.object(graph_module, "ending_judge", end):
                        app = build_compiled_graph()
                        out = app.invoke(inp)
    end.assert_called_once()
    mem.assert_not_called()
    assert out["intent"] == "表白"
    assert out["ending_result"] == "HE"
    assert out["ending_evaluation"] == "评价"
