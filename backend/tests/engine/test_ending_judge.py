from __future__ import annotations

from unittest.mock import patch

from app.engine.nodes import ending_judge as ending_judge_module
from app.engine.state import HiddenState, minimal_conversation_state


def _hs(
    comfort: float = 70.0,
    interest: float = 70.0,
    trust: float = 70.0,
    alertness: float = 30.0,
    baseline: float = 50.0,
) -> HiddenState:
    return {
        "comfort": comfort,
        "interest": interest,
        "trust": trust,
        "alertness": alertness,
        "baseline_compatibility": baseline,
    }


def test_classify_he_for_accept_stance() -> None:
    assert ending_judge_module.classify_ending_result(70.0, _hs(), "accept") == "HE"


def test_classify_ne_when_accept_conflicts_with_guarded_state() -> None:
    guarded = _hs(comfort=35.0, trust=35.0, alertness=75.0)
    assert ending_judge_module.classify_ending_result(45.0, guarded, "accept") == "NE"


def test_classify_ne_for_delay_stance() -> None:
    assert ending_judge_module.classify_ending_result(55.0, _hs(), "delay") == "NE"


def test_classify_be_for_reject_under_high_alertness() -> None:
    hidden = _hs(alertness=80.0)
    assert ending_judge_module.classify_ending_result(45.0, hidden, "reject") == "BE"


def test_classify_ne_for_soft_rejection_without_breaking_state() -> None:
    assert ending_judge_module.classify_ending_result(55.0, _hs(), "reject") == "NE"


def test_classify_ne_for_ambiguous_stance_with_ok_state() -> None:
    assert ending_judge_module.classify_ending_result(55.0, _hs(), "ambiguous") == "NE"


def test_classify_be_for_ambiguous_stance_with_very_low_heartbeat() -> None:
    assert ending_judge_module.classify_ending_result(30.0, _hs(), "ambiguous") == "BE"


def test_classify_he_xixifailcase_regression() -> None:
    """回归：嘻嘻「都答应了，笨蛋」—— stance=accept + 健康状态应得 HE。"""
    hs = _hs(comfort=68.0, trust=59.0, alertness=32.0)
    assert ending_judge_module.classify_ending_result(72.0, hs, "accept") == "HE"


def test_ending_judge_returns_non_empty_evaluation() -> None:
    state = minimal_conversation_state()
    state["character_reply"] = "那我们试试吧"
    state["confession_response"] = "accept"
    state["new_heartbeat_score"] = 68.0
    state["new_hidden_state"] = _hs()
    with patch.object(ending_judge_module, "read_prompt", return_value="R={ending_result}"):
        # call_llm 现在被调用两次：第一次生成 ending_evaluation，第二次生成 user_review
        with patch.object(ending_judge_module, "call_llm", side_effect=["  结局评价正文  ", "  复盘文本  "]) as m:
            out = ending_judge_module.ending_judge(state)
    assert m.call_count == 2
    assert out["ending_result"] == "HE"
    assert out["ending_evaluation"] == "结局评价正文"
    assert out["user_review"] == "复盘文本"


def test_ending_judge_prompts_receive_relationship_context() -> None:
    state = minimal_conversation_state()
    state["recent_messages"] = [
        {"role": "user", "content": "前序用户消息", "round_number": 1},
        {"role": "character", "content": "前序角色回应", "round_number": 1},
    ]
    state["state_changes"] = {
        "comfort_delta": -1,
        "interest_delta": 0,
        "trust_delta": -1,
        "alertness_delta": 1,
        "reason": "前序互动影响了本轮表白",
    }
    state["character_reply"] = "我们慢一点"
    state["new_heartbeat_score"] = 50.0
    state["new_hidden_state"] = _hs()

    with patch.object(
        ending_judge_module,
        "read_prompt",
        side_effect=["评价上下文={relationship_context}", "复盘上下文={relationship_context}"],
    ):
        with patch.object(ending_judge_module, "call_llm", side_effect=["评价", "复盘"]) as m:
            ending_judge_module.ending_judge(state)

    evaluation_prompt = m.call_args_list[0].args[0][0]["content"]
    review_prompt = m.call_args_list[1].args[0][0]["content"]
    assert "前序用户消息" in evaluation_prompt
    assert "前序角色回应" in evaluation_prompt
    assert "前序互动影响了本轮表白" in evaluation_prompt
    assert "前序用户消息" in review_prompt
    assert "前序互动影响了本轮表白" in review_prompt


def test_ending_judge_empty_template_skips_llm() -> None:
    state = minimal_conversation_state()
    state["character_reply"] = "我有点喜欢你，但我们慢一点"
    state["confession_response"] = "delay"
    state["new_heartbeat_score"] = 50.0
    state["new_hidden_state"] = _hs()
    with patch.object(ending_judge_module, "read_prompt", return_value="   \n"):
        with patch.object(ending_judge_module, "call_llm", return_value="x") as m:
            out = ending_judge_module.ending_judge(state)
    m.assert_not_called()
    assert out["ending_result"] == "NE"
    assert out["ending_evaluation"] == "（评价暂缺）"
