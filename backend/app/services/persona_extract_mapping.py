"""persona_extract_v0.6 → 现有 Persona 扁平列的派生映射（列表/兼容用）。

单一事实来源为 extract_snapshot；扁平列为派生摘要。"""
from __future__ import annotations

from app.schemas.persona_extract_v06 import HiddenLayerV06, PersonaExtractV06, VisibleLayerV06


def _join_nonempty(parts: list[str], sep: str = "\n") -> str:
    return sep.join(p.strip() for p in parts if p and str(p).strip())


def visible_layer_to_flat_text(visible: VisibleLayerV06) -> tuple[str, str, str, str, str]:
    """返回 (identity_summary, personality_summary, interests, chat_style, visible_background)。"""
    bi = visible.basic_info
    identity_parts: list[str] = []
    if bi.gender:
        identity_parts.append(f"性别：{bi.gender}")
    if bi.age_or_life_stage:
        identity_parts.append(f"年龄/阶段：{bi.age_or_life_stage}")
    if bi.identity_role:
        identity_parts.append(f"身份：{bi.identity_role}")
    if bi.location_context:
        identity_parts.append(f"环境：{bi.location_context}")
    if bi.relationship_status:
        identity_parts.append(f"感情状态：{bi.relationship_status}")
    ru = visible.relationship_with_user
    if ru.known_context:
        identity_parts.append(f"认识关系：{ru.known_context}")
    if ru.interaction_frequency:
        identity_parts.append(f"互动频率：{ru.interaction_frequency}")
    if ru.current_interaction_summary:
        identity_parts.append(f"互动概况：{ru.current_interaction_summary}")

    identity_summary = _join_nonempty(identity_parts)

    personality_summary = _join_nonempty(visible.explicit_personality_notes)

    interests = _join_nonempty(visible.explicit_interests)

    obs = visible.observable_chat_style
    chat_parts: list[str] = []
    if obs.message_length:
        chat_parts.append(f"回复长度：{obs.message_length}")
    if obs.emoji_usage:
        chat_parts.append(f"表情：{obs.emoji_usage}")
    if obs.initiative_pattern:
        chat_parts.append(f"主动程度：{obs.initiative_pattern}")
    if obs.expression_features:
        chat_parts.append("表达特征：" + "；".join(obs.expression_features))
    if obs.typical_phrases:
        chat_parts.append("常用表达：" + "；".join(obs.typical_phrases[:12]))
    chat_style = _join_nonempty(chat_parts)

    vb = (visible.visible_background or "").strip()

    return identity_summary, personality_summary, interests, chat_style, vb


def hidden_layer_to_flat_strings(hidden: HiddenLayerV06) -> tuple[str, str, str, str, str]:
    """映射到 Persona 隐藏层五个文本列。"""
    ir = hidden.initial_relation_state
    tendency = (ir.initial_relation_tendency or "").strip()
    impression = (ir.initial_impression_baseline or "").strip()

    ic = hidden.inferred_core_profile
    judgment = (ic.summary or "").strip()
    if ic.profile_tags:
        if judgment:
            judgment += "\n标签：" + "、".join(ic.profile_tags[:20])
        else:
            judgment = "标签：" + "、".join(ic.profile_tags[:20])

    pp = hidden.pacing_profile
    pacing_parts = [pp.pacing_tolerance, pp.boundary_sensitivity, pp.confession_threshold]
    pacing = _join_nonempty([str(x) for x in pacing_parts if x and x != "unknown"], sep=" / ")

    ip = hidden.interaction_preferences
    sens_parts = list(ip.sensitive_topics[:20])
    if ip.positive_interaction_cues:
        sens_parts.append("正向线索：" + "；".join(ip.positive_interaction_cues[:8]))
    if ip.negative_interaction_cues:
        sens_parts.append("负向线索：" + "；".join(ip.negative_interaction_cues[:8]))
    sensitivity = _join_nonempty(sens_parts, sep="\n")

    return tendency, impression, judgment, pacing, sensitivity


def extract_to_persona_flat_fields(extract: PersonaExtractV06) -> dict[str, object]:
    """生成写入 Persona ORM 的扁平字段字典（含 extract_snapshot）。"""
    vis = extract.visible_layer
    hid = extract.hidden_layer

    display_name = (vis.display_name or "").strip() or "未命名"
    identity_summary, personality_summary, interests, chat_style, visible_background = (
        visible_layer_to_flat_text(vis)
    )
    tendency, impression, judgment, pacing, sensitivity = hidden_layer_to_flat_strings(hid)

    evolution = {
        "schema_version": extract.schema_version,
        "evolution_tendency": extract.hidden_layer.evolution_tendency.model_dump(mode="json"),
        "initial_hidden_state": extract.hidden_layer.initial_relation_state.initial_hidden_state.model_dump(
            mode="json"
        ),
    }

    return {
        "display_name": display_name[:128],
        "identity_summary": identity_summary,
        "personality_summary": personality_summary,
        "interests": interests,
        "chat_style": chat_style,
        "visible_background": visible_background,
        "hidden_initial_tendency": tendency or "中性",
        "hidden_impression_baseline": impression or "普通起点",
        "hidden_key_judgment": judgment or "观察期",
        "hidden_pacing_tolerance": pacing or "medium",
        "hidden_sensitivity_points": sensitivity or "—",
        "hidden_evolution_params": evolution,
        "extract_snapshot": extract.model_dump(mode="json"),
    }
