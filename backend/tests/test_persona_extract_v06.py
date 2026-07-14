"""persona_extract_v0.6 默认结构与解析冒烟测试。"""

import json

import pytest

from app.schemas.persona_extract_v06 import SCHEMA_VERSION, PersonaExtractV06, default_persona_extract_v06
from app.services.persona_extract_parse import parse_persona_extract_v06


CANONICAL_JSON = r"""
{
  "schema_version": "persona_extract_v0.6",
  "visible_layer": {
    "display_name": null,
    "basic_info": {
      "gender": null,
      "age_or_life_stage": null,
      "identity_role": null,
      "location_context": null,
      "relationship_status": null
    },
    "relationship_with_user": {
      "known_context": null,
      "interaction_frequency": null,
      "current_interaction_summary": null
    },
    "explicit_personality_notes": [],
    "explicit_interests": [],
    "explicit_preferences": {
      "likes": [],
      "dislikes": []
    },
    "observable_chat_style": {
      "message_length": null,
      "emoji_usage": null,
      "initiative_pattern": null,
      "expression_features": [],
      "typical_phrases": []
    },
    "visible_background": null
  },
  "hidden_layer": {
    "inferred_core_profile": {
      "summary": null,
      "profile_tags": [],
      "emotional_expression_style": "unknown",
      "social_energy_level": "unknown",
      "self_protection_level": "unknown",
      "intimacy_attitude": "unknown"
    },
    "initial_relation_state": {
      "initial_relation_tendency": null,
      "initial_impression_baseline": null,
      "initial_hidden_state": {
        "comfort": 50,
        "interest": 50,
        "trust": 50,
        "alertness": 50,
        "baseline_compatibility": 50
      }
    },
    "interaction_preferences": {
      "positive_interaction_cues": [],
      "negative_interaction_cues": [],
      "sensitive_topics": []
    },
    "pacing_profile": {
      "pacing_tolerance": "unknown",
      "boundary_sensitivity": "unknown",
      "confession_threshold": "unknown"
    },
    "evolution_tendency": {
      "comfort_growth_rate": "unknown",
      "trust_growth_rate": "unknown",
      "interest_volatility": "unknown",
      "alertness_trigger_level": "unknown",
      "repair_difficulty": "unknown",
      "negative_memory_weight": "unknown"
    },
    "distinctive_hidden_notes": []
  }
}
"""


def test_default_factory_matches_schema_version() -> None:
    ex = default_persona_extract_v06()
    assert ex.schema_version == SCHEMA_VERSION == "persona_extract_v0.6"


def test_parse_roundtrip_json_string() -> None:
    raw = json.dumps(json.loads(CANONICAL_JSON))
    ex = parse_persona_extract_v06(raw)
    assert isinstance(ex, PersonaExtractV06)
    assert ex.hidden_layer.inferred_core_profile.emotional_expression_style == "unknown"


def test_parse_strips_fence() -> None:
    raw = "```json\n" + json.dumps(json.loads(CANONICAL_JSON)) + "\n```"
    ex = parse_persona_extract_v06(raw)
    assert ex.schema_version == "persona_extract_v0.6"


def test_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="抽取 JSON"):
        parse_persona_extract_v06("not json")
