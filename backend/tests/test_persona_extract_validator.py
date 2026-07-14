"""persona_extract_validator 宽松管线测试。"""

from __future__ import annotations

import json
import logging

import pytest

from app.engine.persona_extract_validator import validate_and_normalize_persona_extract
from app.schemas.persona_extract_v06 import SCHEMA_VERSION, default_persona_extract_v06


def test_extra_fields_pruned_keeps_core_payload() -> None:
    """A：多余字段丢弃，主体合法，不应整份空白默认。"""
    raw = {
        "schema_version": SCHEMA_VERSION,
        "model_extra_top_level": True,
        "visible_layer": {
            "display_name": "小艾",
            "noise_field": 123,
            "basic_info": {"gender": "女"},
            "relationship_with_user": {},
            "explicit_personality_notes": [],
            "explicit_interests": [],
            "explicit_preferences": {"likes": [], "dislikes": []},
            "observable_chat_style": {
                "message_length": "medium",
                "emoji_usage": "low",
                "initiative_pattern": "balanced",
                "expression_features": [],
                "typical_phrases": [],
            },
            "visible_background": None,
        },
        "hidden_layer": {},
    }
    out = validate_and_normalize_persona_extract(raw)
    assert out["schema_version"] == SCHEMA_VERSION
    assert "model_extra_top_level" not in out
    assert "noise_field" not in out["visible_layer"]
    assert out["visible_layer"]["display_name"] == "小艾"
    assert out["visible_layer"]["basic_info"]["gender"] == "女"


def test_basic_info_wrong_type_restores_default_object() -> None:
    """B：basic_info 类型错误 => 恢复默认对象整体成功。"""
    raw = {
        "schema_version": SCHEMA_VERSION,
        "visible_layer": {"basic_info": "乱写一整段"},
        "hidden_layer": {},
    }
    out = validate_and_normalize_persona_extract(raw)
    bi = out["visible_layer"]["basic_info"]
    assert isinstance(bi, dict)
    assert bi["gender"] is None
    assert bi["age_or_life_stage"] is None


def test_merge_prune_export() -> None:
    from app.engine.persona_extract_validator import _merge_and_prune_to_schema

    template = default_persona_extract_v06().model_dump(mode="json")
    pruned = _merge_and_prune_to_schema({"extra": 1, "visible_layer": {}}, template)
    assert "extra" not in pruned


def test_nullable_string_wrong_type_becomes_none() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    raw["visible_layer"]["basic_info"]["gender"] = ["oops"]
    raw["hidden_layer"]["inferred_core_profile"]["summary"] = 123
    out = validate_and_normalize_persona_extract(raw)
    assert out["visible_layer"]["basic_info"]["gender"] is None
    assert out["hidden_layer"]["inferred_core_profile"]["summary"] is None


def test_visible_enum_wrong_type_none_hidden_enum_unknown() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    raw["visible_layer"]["observable_chat_style"]["message_length"] = True
    raw["hidden_layer"]["inferred_core_profile"]["emotional_expression_style"] = ["not", "str"]
    out = validate_and_normalize_persona_extract(raw)
    assert out["visible_layer"]["observable_chat_style"]["message_length"] is None
    assert out["hidden_layer"]["inferred_core_profile"]["emotional_expression_style"] == "unknown"


def test_fence_and_multibrace_raw_decode() -> None:
    inner = default_persona_extract_v06().model_dump(mode="json")
    inner["visible_layer"]["display_name"] = "FromFence"
    dumped = json.dumps(inner, ensure_ascii=False)
    s = '前文说明 {"broken": }\n```json\n' + dumped + "\n```"
    out = validate_and_normalize_persona_extract(s)
    assert out["visible_layer"]["display_name"] == "FromFence"


def test_initiative_unclear_preserved() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    raw["visible_layer"]["observable_chat_style"]["initiative_pattern"] = "unclear"
    out = validate_and_normalize_persona_extract(raw)
    assert out["visible_layer"]["observable_chat_style"]["initiative_pattern"] == "unclear"


def test_visible_unknown_enums_become_none() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    ocs = raw["visible_layer"]["observable_chat_style"]
    ocs["message_length"] = "unknown"
    ocs["emoji_usage"] = "未知"
    ocs["initiative_pattern"] = "unknown"
    out = validate_and_normalize_persona_extract(raw)
    assert out["visible_layer"]["observable_chat_style"]["message_length"] is None
    assert out["visible_layer"]["observable_chat_style"]["emoji_usage"] is None
    assert out["visible_layer"]["observable_chat_style"]["initiative_pattern"] is None


def test_hidden_invalid_enum_becomes_unknown_str() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    raw["hidden_layer"]["inferred_core_profile"]["emotional_expression_style"] = "not_valid"
    out = validate_and_normalize_persona_extract(raw)
    assert out["hidden_layer"]["inferred_core_profile"]["emotional_expression_style"] == "unknown"


def test_initial_hidden_nan_inf_to_50() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    ihs = raw["hidden_layer"]["initial_relation_state"]["initial_hidden_state"]
    ihs["comfort"] = float("nan")
    ihs["trust"] = float("inf")
    out = validate_and_normalize_persona_extract(raw)
    assert out["hidden_layer"]["initial_relation_state"]["initial_hidden_state"]["comfort"] == 50
    assert out["hidden_layer"]["initial_relation_state"]["initial_hidden_state"]["trust"] == 50


def test_string_list_drops_non_strings_dedupe() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    raw["visible_layer"]["explicit_personality_notes"] = ["a", " a ", "a", "暂无", "", 42, {"x": 1}]
    out = validate_and_normalize_persona_extract(raw)
    assert out["visible_layer"]["explicit_personality_notes"] == ["a"]


def test_typical_phrases_not_keyword_filtered_and_no_standalone_qishi() -> None:
    raw = default_persona_extract_v06().model_dump(mode="json")
    raw["visible_layer"]["observable_chat_style"]["typical_phrases"] = ["这其实很正常"]
    out = validate_and_normalize_persona_extract(raw)
    assert "这其实很正常" in out["visible_layer"]["observable_chat_style"]["typical_phrases"]


def test_debug_log_no_full_raw(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    long_noise = "x" * 800
    validate_and_normalize_persona_extract(long_noise)
    records = [r for r in caplog.records if r.name == "app.engine.persona_extract_validator"]
    assert records
    msg = records[0].getMessage()
    assert long_noise not in msg
    assert "…" in msg or len(msg) < len(long_noise)


def test_strict_parse_still_importable() -> None:
    from app.services.persona_extract_parse import parse_persona_extract_v06

    assert callable(parse_persona_extract_v06)
