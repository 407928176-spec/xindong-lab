"""LangGraph 状态类型：与 PHASE5_DESIGN.md 第 2 节字段名保持一致。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict


class HiddenState(TypedDict):
    comfort: float
    interest: float
    trust: float
    alertness: float
    baseline_compatibility: float


class StateChanges(TypedDict):
    comfort_delta: float
    interest_delta: float
    trust_delta: float
    alertness_delta: float
    reason: str


class ConversationState(TypedDict):
    # 输入层（每轮由 API 层填入）
    character_id: str
    user_message: str
    current_round: int
    # 匿名设备用户（附件签名与校验）；无附件时可为空串
    anon_user_id: NotRequired[str]
    pending_attachment_ids: NotRequired[list[str]]
    draft_turn_id: NotRequired[str]
    # load_context 填入：发往模型的本轮 user 消息 content（str 或 OpenAI 多模态 list）
    user_llm_content: NotRequired[str | list[dict[str, Any]]]

    # 上下文层（从 DB 加载，喂给 LLM）
    system_prompt: str
    persona_prompt: str
    hidden_state: HiddenState
    relationship_state_prompt: NotRequired[str]
    long_term_memory: str
    recent_messages: list[dict[str, Any]]

    # 节点输出层（逐步填充）
    character_reply: str
    # True：本轮角色主动无文字回应（与 character_reply=="" 成对出现）；仅当模型输出精确 <NO_REPLY>。
    character_no_reply: NotRequired[bool]
    intent: str
    state_changes: StateChanges
    new_hidden_state: HiddenState
    new_heartbeat_score: float
    # True：本轮 memory_manager 判定 recent_messages 字符总和 ≥ 阈值；API 应在整图 invoke 结束且本轮消息已落库后入队 BackgroundTasks（不表示压缩已完成）。False：未触发。
    should_update_memory: bool

    # evaluate_state 判定的角色对表白的态度（表白 intent 时有效）：accept / reject / delay / ambiguous
    confession_response: str

    # 结局层（仅表白时填充）
    ending_result: str | None
    ending_evaluation: str | None
    user_review: str | None

    # 持久化回执（仅 save_and_respond 写入；不进 prompt，见 prompt_template）
    persisted_user_message_id: NotRequired[str]
    persisted_assistant_message_id: NotRequired[str]
    persisted_round: NotRequired[int]
    persisted_heartbeat_score: NotRequired[int]
    persisted_user_message_at: NotRequired[datetime]
    persisted_assistant_message_at: NotRequired[datetime]


def minimal_conversation_state() -> ConversationState:
    """供步骤 5.1 骨架测试与本地调试：填满所有必填字段。"""
    hs: HiddenState = {
        "comfort": 50.0,
        "interest": 50.0,
        "trust": 50.0,
        "alertness": 50.0,
        "baseline_compatibility": 50.0,
    }
    sc: StateChanges = {
        "comfort_delta": 0.0,
        "interest_delta": 0.0,
        "trust_delta": 0.0,
        "alertness_delta": 0.0,
        "reason": "",
    }
    return {
        "character_id": "test-character",
        "user_message": "你好",
        "current_round": 1,
        "system_prompt": "",
        "persona_prompt": "",
        "hidden_state": hs,
        "relationship_state_prompt": "",
        "long_term_memory": "",
        "recent_messages": [],
        "character_reply": "",
        "character_no_reply": False,
        "intent": "",
        "state_changes": sc,
        "new_hidden_state": hs,
        "new_heartbeat_score": 50.0,
        "should_update_memory": False,
        "confession_response": "ambiguous",
        "ending_result": None,
        "ending_evaluation": None,
        "user_review": None,
    }
