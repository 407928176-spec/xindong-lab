from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.engine.nodes.save_and_respond import _save_turn_with_session
from app.engine.state import ConversationState, HiddenState, StateChanges
from app.models.character import Character
from app.models.ending import Ending
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


def _state_for_save(character_id: str, user: str, reply: str, hb: float) -> ConversationState:
    hs: HiddenState = {
        "comfort": 10.0,
        "interest": 20.0,
        "trust": 30.0,
        "alertness": 40.0,
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
        "character_id": character_id,
        "user_message": user,
        "current_round": 0,
        "system_prompt": "",
        "persona_prompt": "",
        "hidden_state": hs,
        "long_term_memory": "",
        "recent_messages": [],
        "character_reply": reply,
        "character_no_reply": False,
        "intent": "",
        "state_changes": sc,
        "new_hidden_state": hs,
        "new_heartbeat_score": hb,
        "should_update_memory": False,
        "ending_result": None,
        "ending_evaluation": None,
    }


def test_save_turn_writes_pair_same_round_and_returns_persisted(memory_session: Session) -> None:
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
    memory_session.commit()

    out = _save_turn_with_session(memory_session, _state_for_save(cid, "u1", "r1", 55.4))
    assert out["persisted_round"] == 1
    assert out["persisted_heartbeat_score"] == 55
    uid, aid = out["persisted_user_message_id"], out["persisted_assistant_message_id"]

    msgs = list(memory_session.scalars(select(Message).where(Message.character_id == cid)))
    assert len(msgs) == 2
    roles = {m.role for m in msgs}
    assert roles == {MessageRole.USER.value, MessageRole.CHARACTER.value}
    assert {m.round_number for m in msgs} == {1}

    out2 = _save_turn_with_session(memory_session, _state_for_save(cid, "u2", "r2", 60.0))
    assert out2["persisted_round"] == 2
    for k in ("persisted_user_message_at", "persisted_assistant_message_at"):
        assert hasattr(out2[k], "isoformat")

    u1 = memory_session.get(Message, uid)
    assert u1 is not None
    assert u1.content == "u1"


def test_save_turn_no_reply_sets_internal_phase_change(memory_session: Session) -> None:
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
    memory_session.commit()

    st = _state_for_save(cid, "u-silent", "", 50.0)
    st["character_no_reply"] = True
    _save_turn_with_session(memory_session, st)
    msgs = list(memory_session.scalars(select(Message).where(Message.character_id == cid)))
    char = next(m for m in msgs if m.role == MessageRole.CHARACTER.value)
    assert char.content == ""
    assert char.internal_phase_change == {"no_reply": True}


def test_save_turn_with_ending_persists_ending_row(memory_session: Session) -> None:
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
    memory_session.commit()

    st = _state_for_save(cid, "confess", "reply", 80.0)
    st["ending_result"] = "HE"
    st["ending_evaluation"] = "ending evaluation"
    _save_turn_with_session(memory_session, st)

    character = memory_session.get(Character, cid)
    assert character is not None
    assert character.is_ended is True
    assert character.status == CharacterStatus.ENDING_UNREAD.value

    ending = memory_session.scalar(select(Ending).where(Ending.character_id == cid))
    assert ending is not None
    assert ending.ending_kind == "HE"
    assert ending.content == "ending evaluation"


def test_save_turn_with_ne_ending_also_stays_ending_unread(memory_session: Session) -> None:
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
    memory_session.commit()

    st = _state_for_save(cid, "confess", "slow down", 55.0)
    st["ending_result"] = "NE"
    st["ending_evaluation"] = "ne ending evaluation"
    _save_turn_with_session(memory_session, st)

    character = memory_session.get(Character, cid)
    assert character is not None
    assert character.is_ended is True
    assert character.status == CharacterStatus.ENDING_UNREAD.value

    ending = memory_session.scalar(select(Ending).where(Ending.character_id == cid))
    assert ending is not None
    assert ending.ending_kind == "NE"
    assert ending.content == "ne ending evaluation"
