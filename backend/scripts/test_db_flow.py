"""最小数据库读写验证：写入人设、角色、消息、复盘并读回。

默认使用独立 SQLite 文件 `backend/data/test_flow.db`，并会清空后重建表结构，
避免污染 `app.db`；如需改用其他路径，可先设置环境变量 `DATABASE_URL`。

用法（在 `backend/` 目录下、已激活虚拟环境）::

    python scripts/test_db_flow.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_root))

    # 必须在首次导入 `app.db.session` 之前设置，否则引擎会按默认 URL 初始化
    test_db = backend_root / "data" / "test_flow.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db.as_posix()}"

    from sqlalchemy import select  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.db.base import Base  # noqa: PLC0415
    from app.db.session import SessionLocal, engine  # noqa: PLC0415
    import app.models  # noqa: F401, PLC0415

    from app.models.character import Character  # noqa: PLC0415
    from app.models.ending import Ending  # noqa: PLC0415
    from app.models.enums import (  # noqa: PLC0415
        CharacterStatus,
        EndingKind,
        LoveSignalMark,
        MessageRole,
        PersonaCreationMethod,
        ReviewType,
    )
    from app.models.message import Message  # noqa: PLC0415
    from app.models.persona import Persona  # noqa: PLC0415
    from app.models.review import Review  # noqa: PLC0415

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session: Session = SessionLocal()
    try:
        persona = Persona(
            creation_method=PersonaCreationMethod.TEXT_DESCRIPTION.value,
            display_name="示例人设",
            identity_summary="学生",
            personality_summary="外向",
            interests="电影",
            chat_style="轻松",
            visible_background="同城",
            hidden_initial_tendency="中性偏冷",
            hidden_impression_baseline="普通朋友",
            hidden_key_judgment="观察期",
            hidden_pacing_tolerance="中等",
            hidden_sensitivity_points="不喜欢被追问隐私",
            hidden_evolution_params={"version": 1, "weights": {"comfort": 0.2}},
            raw_source_material="用户输入：……",
        )

        character = Character(
            persona=persona,
            display_name="示例角色线",
            status=CharacterStatus.IN_PROGRESS.value,
            hidden_state_snapshot={
                "comfort": 60,
                "interest": 55,
                "trust": 50,
                "vigilance": 40,
                "baseline_match": 58,
            },
            long_term_memory=None,
            memory_updated_at_round=0,
        )

        session.add(persona)
        session.add(character)
        session.flush()

        m1 = Message(
            character=character,
            role=MessageRole.USER.value,
            content="你好呀",
            round_number=1,
            love_signal_mark=LoveSignalMark.NONE.value,
            internal_phase_change=None,
        )
        m2 = Message(
            character=character,
            role=MessageRole.CHARACTER.value,
            content="嗨，今天怎么样？",
            round_number=1,
            love_signal_mark=LoveSignalMark.NONE.value,
            internal_phase_change={"note": "占位：阶段 2 不做状态机"},
        )

        review = Review(
            character=character,
            review_type=ReviewType.SHORT.value,
            content="这是一条短复盘占位内容。",
            analyzed_range={"from_round": 1, "to_round": 2},
        )

        ending = Ending(
            character=character,
            ending_kind=EndingKind.USER_ARCHIVED.value,
            content="占位：终局记录（阶段 2 仅验证写入）。",
        )

        session.add_all([m1, m2, review, ending])
        session.commit()

        loaded_persona = session.get(Persona, persona.id)
        loaded_character = session.get(Character, character.id)
        assert loaded_persona is not None
        assert loaded_character is not None
        assert loaded_character.persona_id == loaded_persona.id
        assert loaded_character.hidden_state_snapshot is not None
        assert loaded_character.hidden_state_snapshot.get("comfort") == 60
        assert loaded_character.long_term_memory is None
        assert loaded_character.memory_updated_at_round == 0

        msgs = list(
            session.scalars(
                select(Message)
                .where(Message.character_id == character.id)
                .order_by(Message.round_number.asc())
            )
        )
        assert len(msgs) == 2

        reviews = list(
            session.scalars(select(Review).where(Review.character_id == character.id))
        )
        assert len(reviews) == 1

        ending_row = session.scalar(select(Ending).where(Ending.character_id == character.id))
        assert ending_row is not None
        assert ending_row.ending_kind == EndingKind.USER_ARCHIVED.value

        print("写入并校验通过：")
        print("- persona_id:", loaded_persona.id)
        print("- character_id:", loaded_character.id)
        print("- messages:", [m.round_number for m in msgs])
        print("- review_type:", reviews[0].review_type)
        print("- ending_kind:", ending_row.ending_kind)
    finally:
        session.close()


if __name__ == "__main__":
    main()
