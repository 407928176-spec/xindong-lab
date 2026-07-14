from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — 注册 ORM 到 Base.metadata
from app.db.base import Base
from app.engine.no_reply import NO_REPLY_LLM_PLACEHOLDER
from app.engine.nodes.load_context import build_relationship_state_prompt, load_context_from_db
from app.engine.state import ConversationState, HiddenState, StateChanges
from app.models.character import Character
from app.models.enums import CharacterStatus, MessageRole
from app.models.message import Message
from app.models.persona import Persona


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionMaker = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)
    s = SessionMaker()
    try:
        yield s
    finally:
        s.close()


def _minimal_state(character_id: str) -> ConversationState:
    hs: HiddenState = {
        "comfort": 1.0,
        "interest": 2.0,
        "trust": 3.0,
        "alertness": 4.0,
        "baseline_compatibility": 5.0,
    }
    sc: StateChanges = {
        "comfort_delta": 0.0,
        "interest_delta": 0.0,
        "trust_delta": 0.0,
        "alertness_delta": 0.0,
        "reason": "",
    }
    return {
        "character_id": character_id,
        "user_message": "hi",
        "current_round": 999,
        "system_prompt": "",
        "persona_prompt": "",
        "hidden_state": hs,
        "long_term_memory": "",
        "recent_messages": [],
        "character_reply": "",
        "intent": "",
        "state_changes": sc,
        "new_hidden_state": hs,
        "new_heartbeat_score": 50.0,
        "should_update_memory": False,
        "ending_result": None,
        "ending_evaluation": None,
    }


def test_relationship_state_prompt_high_state_allows_active_confirmation() -> None:
    text = build_relationship_state_prompt(
        {
            "comfort": 75.0,
            "interest": 80.0,
            "trust": 70.0,
            "alertness": 25.0,
            "baseline_compatibility": 75.0,
        }
    )
    assert "主动确认关系" in text
    assert "默认接受" in text


def test_relationship_state_prompt_guarded_state_slows_confession() -> None:
    text = build_relationship_state_prompt(
        {
            "comfort": 35.0,
            "interest": 55.0,
            "trust": 35.0,
            "alertness": 75.0,
            "baseline_compatibility": 45.0,
        }
    )
    assert "避免快速确认关系" in text
    assert "拒绝" in text


def test_load_context_from_db_fills_fields(memory_session: Session) -> None:
    pid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    persona = Persona(
        id=pid,
        display_name="小测试",
        identity_summary="学生",
        personality_summary="内向",
        interests="读书",
        chat_style="短句",
        visible_background="校园",
        hidden_initial_tendency="慢热",
        hidden_impression_baseline="中性",
        hidden_key_judgment="观察中",
        hidden_pacing_tolerance="不喜追问",
        hidden_sensitivity_points="家庭话题",
    )
    memory_session.add(persona)
    char = Character(
        id=cid,
        persona_id=pid,
        display_name="实例A",
        status=CharacterStatus.IN_PROGRESS.value,
        hidden_state_snapshot={
            "comfort": 60.0,
            "interest": 55.0,
            "trust": 40.0,
            "alertness": 30.0,
            "baseline_compatibility": 70.0,
        },
        long_term_memory="  摘要一行  ",
    )
    memory_session.add(char)
    memory_session.add_all(
        [
            Message(
                character_id=cid,
                role=MessageRole.USER.value,
                content="你好",
                round_number=1,
            ),
            Message(
                character_id=cid,
                role=MessageRole.CHARACTER.value,
                content="你好呀",
                round_number=2,
            ),
            Message(
                character_id=cid,
                role=MessageRole.USER.value,
                content="在吗",
                round_number=3,
            ),
        ]
    )
    memory_session.commit()

    state = _minimal_state(cid)
    patch = load_context_from_db(memory_session, state)

    assert patch["system_prompt"]
    assert "小测试" in patch["persona_prompt"] and "学生" in patch["persona_prompt"]
    assert patch["hidden_state"]["comfort"] == 60.0
    assert "当前关系状态" in patch["relationship_state_prompt"]
    assert patch["long_term_memory"] == "摘要一行"
    assert patch["current_round"] == 2
    assert patch["recent_messages"] == [
        {"role": "user", "content": "你好", "is_no_reply": False},
        {"role": "character", "content": "你好呀", "is_no_reply": False},
        {"role": "user", "content": "在吗", "is_no_reply": False},
    ]


def test_load_context_no_reply_character_uses_llm_placeholder(memory_session: Session) -> None:
    pid, cid = str(uuid.uuid4()), str(uuid.uuid4())
    memory_session.add(
        Persona(
            id=pid,
            display_name="P",
            identity_summary="i",
            personality_summary="p",
            interests="in",
            chat_style="c",
            visible_background="vb",
            hidden_initial_tendency="h1",
            hidden_impression_baseline="h2",
            hidden_key_judgment="h3",
            hidden_pacing_tolerance="h4",
            hidden_sensitivity_points="h5",
        )
    )
    memory_session.add(
        Character(
            id=cid,
            persona_id=pid,
            display_name="C",
            status=CharacterStatus.IN_PROGRESS.value,
        )
    )
    memory_session.add_all(
        [
            Message(
                character_id=cid,
                role=MessageRole.USER.value,
                content="你在吗",
                round_number=1,
            ),
            Message(
                character_id=cid,
                role=MessageRole.CHARACTER.value,
                content="",
                round_number=1,
                internal_phase_change={"no_reply": True},
            ),
        ]
    )
    memory_session.commit()

    state = _minimal_state(cid)
    patch = load_context_from_db(memory_session, state)
    assert patch["recent_messages"][-1] == {
        "role": MessageRole.CHARACTER.value,
        "content": NO_REPLY_LLM_PLACEHOLDER,
        "is_no_reply": True,
    }


def test_load_context_missing_character_returns_empty(memory_session: Session, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    state = _minimal_state("00000000-0000-0000-0000-000000000000")
    assert load_context_from_db(memory_session, state) == {}
    assert any("not found" in r.message for r in caplog.records)
