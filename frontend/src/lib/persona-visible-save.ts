import type { PersonaExtractV06, VisibleLayerV06 } from "@/types/persona";

/** 与后端 save_persona 可见层非空判定对齐，用于按钮可点状态 */
export function visibleLayerHasMinimumContent(extract: PersonaExtractV06): boolean {
  return visibleLayerHasMinimumContentInner(extract.visible_layer);
}

function visibleLayerHasMinimumContentInner(vl: VisibleLayerV06): boolean {
  if (vl.display_name?.trim() && vl.display_name.trim() !== "未命名") return true;
  const bi = vl.basic_info;
  if (
    bi.gender ||
    bi.age_or_life_stage ||
    bi.identity_role ||
    bi.location_context ||
    bi.relationship_status
  ) {
    return true;
  }
  const ru = vl.relationship_with_user;
  if (ru.known_context || ru.interaction_frequency || ru.current_interaction_summary) {
    return true;
  }
  if (vl.explicit_personality_notes.length) return true;
  if (vl.explicit_interests.length) return true;
  const pref = vl.explicit_preferences;
  if (pref.likes.length || pref.dislikes.length) return true;
  const obs = vl.observable_chat_style;
  if (obs.message_length || obs.emoji_usage || obs.initiative_pattern) return true;
  if (obs.expression_features.length || obs.typical_phrases.length) return true;
  if (vl.visible_background?.trim()) return true;
  return false;
}
