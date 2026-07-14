"""persona_extract_v0.6 结构化契约：与 docs/character_creation_extract_prompt输出格式及说明.md §一/§六 对齐。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "persona_extract_v0.6"


class BasicInfoV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gender: str | None = None
    age_or_life_stage: str | None = None
    identity_role: str | None = None
    location_context: str | None = None
    relationship_status: str | None = None


class RelationshipWithUserV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    known_context: str | None = None
    interaction_frequency: str | None = None
    current_interaction_summary: str | None = None


class ExplicitPreferencesV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)


class ObservableChatStyleV06(BaseModel):
    """observable_chat_style：message_length / emoji_usage / initiative_pattern 可为 null（文档 §二）。"""

    model_config = ConfigDict(extra="forbid")

    message_length: str | None = None
    emoji_usage: str | None = None
    initiative_pattern: str | None = None
    expression_features: list[str] = Field(default_factory=list)
    typical_phrases: list[str] = Field(default_factory=list)


class VisibleLayerV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    name_user_specified: bool = False
    basic_info: BasicInfoV06 = Field(default_factory=BasicInfoV06)
    relationship_with_user: RelationshipWithUserV06 = Field(default_factory=RelationshipWithUserV06)
    explicit_personality_notes: list[str] = Field(default_factory=list)
    explicit_interests: list[str] = Field(default_factory=list)
    explicit_preferences: ExplicitPreferencesV06 = Field(default_factory=ExplicitPreferencesV06)
    observable_chat_style: ObservableChatStyleV06 = Field(default_factory=ObservableChatStyleV06)
    visible_background: str | None = None


class InferredCoreProfileV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    profile_tags: list[str] = Field(default_factory=list)
    emotional_expression_style: str = "unknown"
    social_energy_level: str = "unknown"
    self_protection_level: str = "unknown"
    intimacy_attitude: str = "unknown"


class InitialHiddenStateV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comfort: int = Field(default=50, ge=0, le=100)
    interest: int = Field(default=50, ge=0, le=100)
    trust: int = Field(default=50, ge=0, le=100)
    alertness: int = Field(default=50, ge=0, le=100)
    baseline_compatibility: int = Field(default=50, ge=0, le=100)


class InitialRelationStateV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_relation_tendency: str | None = None
    initial_impression_baseline: str | None = None
    initial_hidden_state: InitialHiddenStateV06 = Field(default_factory=InitialHiddenStateV06)


class InteractionPreferencesV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positive_interaction_cues: list[str] = Field(default_factory=list)
    negative_interaction_cues: list[str] = Field(default_factory=list)
    sensitive_topics: list[str] = Field(default_factory=list)


class PacingProfileV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pacing_tolerance: str = "unknown"
    boundary_sensitivity: str = "unknown"
    confession_threshold: str = "unknown"


class EvolutionTendencyV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comfort_growth_rate: str = "unknown"
    trust_growth_rate: str = "unknown"
    interest_volatility: str = "unknown"
    alertness_trigger_level: str = "unknown"
    repair_difficulty: str = "unknown"
    negative_memory_weight: str = "unknown"


class HiddenLayerV06(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inferred_core_profile: InferredCoreProfileV06 = Field(default_factory=InferredCoreProfileV06)
    initial_relation_state: InitialRelationStateV06 = Field(default_factory=InitialRelationStateV06)
    interaction_preferences: InteractionPreferencesV06 = Field(default_factory=InteractionPreferencesV06)
    pacing_profile: PacingProfileV06 = Field(default_factory=PacingProfileV06)
    evolution_tendency: EvolutionTendencyV06 = Field(default_factory=EvolutionTendencyV06)
    distinctive_hidden_notes: list[str] = Field(default_factory=list)


class PersonaExtractV06(BaseModel):
    """根模型：静默抽取 JSON 校验入口。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["persona_extract_v0.6"] = Field(default="persona_extract_v0.6")
    visible_layer: VisibleLayerV06 = Field(default_factory=VisibleLayerV06)
    hidden_layer: HiddenLayerV06 = Field(default_factory=HiddenLayerV06)


def default_persona_extract_v06() -> PersonaExtractV06:
    """与文档 §六「空白默认」一致的模型实例。"""
    return PersonaExtractV06()

