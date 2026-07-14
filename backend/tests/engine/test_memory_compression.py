from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.engine import memory_compression as memory_compression_module
from app.engine.memory_compression import (
    PAIR_KEEP,
    collect_message_ids_to_keep_last_n_pairs,
    enqueue_long_memory_compression_after_graph,
    run_long_memory_compression_job,
)
from app.engine.state import ConversationState, minimal_conversation_state
from app.models.character import Character
from app.models.enums import CharacterStatus, MessageRole
from app.models.message import Message
from app.models.persona import Persona


@pytest.fixture
def memory_db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionMaker = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)
    s = SessionMaker()
    try:
        yield s
    finally:
        s.close()


def _seed_character_with_messages(
    session: Session,
    *,
    n_pairs: int,
    chars_per_message: int,
) -> str:
    pid, cid = str(uuid.uuid4()), str(uuid.uuid4())
    ch = "x"
    session.add(
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
    session.add(
        Character(
            id=cid,
            persona_id=pid,
            display_name="C",
            status=CharacterStatus.IN_PROGRESS.value,
            long_term_memory="OLD",
        )
    )
    for r in range(n_pairs):
        session.add(
            Message(
                character_id=cid,
                role=MessageRole.USER.value,
                content=ch * chars_per_message,
                round_number=r * 2,
            )
        )
        session.add(
            Message(
                character_id=cid,
                role=MessageRole.CHARACTER.value,
                content=ch * chars_per_message,
                round_number=r * 2 + 1,
            )
        )
    session.commit()
    return cid


def test_collect_message_ids_keeps_last_twenty_pairs(memory_db_session: Session) -> None:
    cid = _seed_character_with_messages(memory_db_session, n_pairs=25, chars_per_message=10)
    msgs = list(memory_db_session.scalars(select(Message).where(Message.character_id == cid).order_by(Message.round_number.asc())))
    assert len(msgs) == 50
    keep = collect_message_ids_to_keep_last_n_pairs(msgs, PAIR_KEEP)
    assert len(keep) == 40
    first_pair_user = msgs[0]
    assert first_pair_user.id not in keep


@patch("app.engine.memory_compression.SessionLocal")
def test_run_compression_updates_memory_and_trims_messages(mock_session_local, memory_db_session: Session) -> None:
    cid = _seed_character_with_messages(memory_db_session, n_pairs=25, chars_per_message=250)
    total = sum(len(m.content) for m in memory_db_session.scalars(select(Message).where(Message.character_id == cid)))
    assert total >= 10_000

    engine = memory_db_session.get_bind()

    def _session_factory() -> Session:
        SessionMaker = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)
        return SessionMaker()

    mock_session_local.side_effect = lambda: _session_factory()

    with patch("app.engine.memory_compression.call_llm", return_value="  NEW_SUMMARY  ") as m_llm:
        run_long_memory_compression_job(cid)

    m_llm.assert_called_once()
    assert m_llm.call_args.kwargs.get("model") is not None

    memory_db_session.expire_all()
    char = memory_db_session.get(Character, cid)
    assert char is not None
    assert char.long_term_memory == "NEW_SUMMARY"

    remaining = list(memory_db_session.scalars(select(Message).where(Message.character_id == cid)))
    assert len(remaining) == 40


def test_enqueue_adds_background_task_when_flag_true() -> None:
    bg: MagicMock = MagicMock()
    state = minimal_conversation_state()
    state["character_id"] = "cid-1"
    state["should_update_memory"] = True
    enqueue_long_memory_compression_after_graph(state, bg)
    bg.add_task.assert_called_once()
    assert bg.add_task.call_args[0][0] == run_long_memory_compression_job
    assert bg.add_task.call_args[0][1] == "cid-1"


def test_enqueue_skips_when_false_or_no_bg() -> None:
    state = minimal_conversation_state()
    state["should_update_memory"] = False
    bg: MagicMock = MagicMock()
    enqueue_long_memory_compression_after_graph(state, bg)
    bg.add_task.assert_not_called()
    enqueue_long_memory_compression_after_graph(state, None)


def test_enqueue_skips_empty_character_id() -> None:
    bg = MagicMock()
    state: ConversationState = minimal_conversation_state()
    state["character_id"] = ""
    state["should_update_memory"] = True
    enqueue_long_memory_compression_after_graph(state, bg)
    bg.add_task.assert_not_called()
