from __future__ import annotations

from unittest.mock import patch

from app.engine import persona_generator


def _character_info() -> dict[str, object]:
    return {"persona_id": "p1", "extract_snapshot": {"schema_version": "persona_extract_v0.6"}}


def test_generate_persona_prompt_returns_short_result() -> None:
    with patch.object(persona_generator, "read_prompt", return_value="模板"):
        with patch.object(persona_generator, "call_llm", return_value="  短人设  ") as m:
            result = persona_generator.generate_persona_prompt(_character_info())

    assert result == "短人设"
    assert m.call_count == 1


def test_generate_persona_prompt_rewrites_when_too_long() -> None:
    long_text = "长" * 2001
    short_text = "短" * 100
    with patch.object(persona_generator, "read_prompt", return_value="模板"):
        with patch.object(persona_generator, "call_llm", side_effect=[long_text, short_text]) as m:
            result = persona_generator.generate_persona_prompt(_character_info())

    assert result == short_text
    assert m.call_count == 2


def test_generate_persona_prompt_falls_back_when_rewrite_still_too_long() -> None:
    long_text = "长" * 2001
    with patch.object(persona_generator, "read_prompt", return_value="模板"):
        with patch.object(persona_generator, "call_llm", side_effect=[long_text, long_text]):
            result = persona_generator.generate_persona_prompt(_character_info())

    assert result == ""
