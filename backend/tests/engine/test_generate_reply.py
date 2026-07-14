from __future__ import annotations

from unittest.mock import patch

from app.engine import message_token_budget as message_token_budget_module
from app.engine.nodes import generate_reply as generate_reply_module
from app.engine.state import minimal_conversation_state
from app.engine.web_context import WebContextBuildResult, WebContextDecision


def test_generate_reply_message_order_and_roles() -> None:
    state = minimal_conversation_state()
    state["persona_prompt"] = "人设层"
    state["hidden_state"] = {
        "comfort": 1.0,
        "interest": 2.0,
        "trust": 3.0,
        "alertness": 4.0,
        "baseline_compatibility": 5.0,
    }
    state["relationship_state_prompt"] = "关系解释"
    state["long_term_memory"] = "摘要"
    state["recent_messages"] = [{"role": "user", "content": "旧问"}, {"role": "character", "content": "旧答"}]
    state["user_message"] = "本轮用户"

    with patch.object(generate_reply_module, "decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
        with patch.object(generate_reply_module, "build_web_context", return_value=WebContextBuildResult("")):
            with patch.object(generate_reply_module, "call_llm", return_value="  模型回  ") as m:
                with patch.object(generate_reply_module, "read_prompt", return_value="通用层"):
                    out = generate_reply_module.generate_reply(state)

    assert out == {"character_reply": "模型回", "character_no_reply": False}
    m.assert_called_once()
    assert m.call_args.kwargs["use_web_search"] is False
    msgs = m.call_args[0][0]
    assert [x["role"] for x in msgs] == ["system", "system", "system", "system", "user", "assistant", "user"]
    assert msgs[0]["content"] == "通用层"
    assert msgs[1]["content"] == "人设层"
    assert "当前关系状态：" in msgs[2]["content"]
    assert "关系解释" in msgs[2]["content"]
    assert msgs[3]["content"] == "长期记忆：摘要"
    assert msgs[-1]["content"] == "本轮用户"


def test_generate_reply_truncates_old_recent_copy() -> None:
    """用固定 token 估算避免超大 tiktoken 编码拖慢 CI。"""
    state = minimal_conversation_state()
    state["persona_prompt"] = "p"
    state["long_term_memory"] = ""
    state["recent_messages"] = [{"role": "user", "content": "a"}, {"role": "character", "content": "b"}] * 30
    state["user_message"] = "最后"

    with patch.object(message_token_budget_module, "estimate_message_dict", return_value=8000):
        with patch.object(message_token_budget_module, "_MAX_CONTEXT_TOKENS", 50_000):
            with patch.object(message_token_budget_module, "_OUTPUT_RESERVE", 0):
                with patch.object(generate_reply_module, "decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
                    with patch.object(generate_reply_module, "build_web_context", return_value=WebContextBuildResult("")):
                        with patch.object(generate_reply_module, "call_llm", return_value="x") as m:
                            with patch.object(generate_reply_module, "read_prompt", return_value="sys"):
                                generate_reply_module.generate_reply(state)

    msgs = m.call_args[0][0]
    assert len(msgs) < 4 + 60 + 1
    assert msgs[-1]["content"] == "最后"


def test_generate_reply_three_calls() -> None:
    with patch.object(generate_reply_module, "decide_web_context", return_value=WebContextDecision(False, "", "无需联网")):
        with patch.object(generate_reply_module, "build_web_context", return_value=WebContextBuildResult("")):
            with patch.object(generate_reply_module, "call_llm", return_value="ok") as m:
                with patch.object(generate_reply_module, "read_prompt", return_value="sys"):
                    for i in range(3):
                        st = minimal_conversation_state()
                        st["user_message"] = f"第{i}轮"
                        generate_reply_module.generate_reply(st)
    assert m.call_count == 3


def test_generate_reply_inserts_web_context_before_user() -> None:
    state = minimal_conversation_state()
    state["user_message"] = "今天的新闻你看了么？"

    with patch.object(generate_reply_module, "decide_web_context", return_value=WebContextDecision(True, "新闻", "需要实时信息")):
        with patch.object(generate_reply_module, "build_web_context", return_value=WebContextBuildResult("新闻资料包")) as web:
            with patch.object(generate_reply_module, "call_llm", return_value="角色回复") as llm:
                with patch.object(generate_reply_module, "read_prompt", return_value="sys"):
                    out = generate_reply_module.generate_reply(state)

    assert out == {"character_reply": "角色回复", "character_no_reply": False}
    web.assert_called_once()
    assert web.call_args.args[0] is state
    assert web.call_args.args[1].should_search is True
    llm.assert_called_once()
    assert llm.call_args.kwargs["use_web_search"] is False
    msgs = llm.call_args.args[0]
    assert msgs[-2]["role"] == "system"
    assert "新闻资料包" in msgs[-2]["content"]
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "今天的新闻你看了么？"


def test_stream_character_reply_uses_web_context_without_final_search() -> None:
    state = minimal_conversation_state()
    state["user_message"] = "今天的天气怎么样？"

    with patch.object(generate_reply_module, "decide_web_context", return_value=WebContextDecision(True, "新闻", "需要实时信息")):
        with patch.object(generate_reply_module, "build_web_context", return_value=WebContextBuildResult("天气资料包")):
            with patch.object(generate_reply_module, "call_llm", return_value=iter(["你", "好"])) as llm:
                with patch.object(generate_reply_module, "read_prompt", return_value="sys"):
                    chunks = list(generate_reply_module.stream_character_reply_tokens(state))

    assert chunks == ["你", "好"]
    llm.assert_called_once()
    assert llm.call_args.kwargs["stream"] is True
    assert llm.call_args.kwargs["use_web_search"] is False
