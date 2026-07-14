"""LangGraph 状态图：含 evaluate_state 后条件路由与 ending_judge（步骤 5.6）。"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.engine.nodes.ending_judge import ending_judge
from app.engine.nodes.evaluate_state import evaluate_state
from app.engine.nodes.generate_reply import generate_reply
from app.engine.nodes.load_context import load_context
from app.engine.nodes.memory_manager import memory_manager
from app.engine.nodes.save_and_respond import save_and_respond
from app.engine.state import ConversationState


def route_after_evaluation(state: ConversationState) -> Literal["ending_judge", "memory_manager"]:
    """用户/模型主动表白走结局判定；预留「角色表白」与 evaluate_state_prompt 定稿对齐。"""
    intent = (state.get("intent") or "").strip()
    if intent in ("表白", "角色表白"):
        return "ending_judge"
    return "memory_manager"


def build_compiled_graph():
    """编译对话主链：load → reply → evaluate →（表白|角色表白→ending_judge | 否则→memory_manager）→ save。"""
    graph = StateGraph(ConversationState)
    graph.add_node("load_context", load_context)
    graph.add_node("generate_reply", generate_reply)
    graph.add_node("evaluate_state", evaluate_state)
    graph.add_node("memory_manager", memory_manager)
    graph.add_node("ending_judge", ending_judge)
    graph.add_node("save_and_respond", save_and_respond)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "generate_reply")
    graph.add_edge("generate_reply", "evaluate_state")
    graph.add_conditional_edges(
        "evaluate_state",
        route_after_evaluation,
        {
            "ending_judge": "ending_judge",
            "memory_manager": "memory_manager",
        },
    )
    graph.add_edge("memory_manager", "save_and_respond")
    graph.add_edge("ending_judge", "save_and_respond")
    graph.add_edge("save_and_respond", END)

    return graph.compile()
