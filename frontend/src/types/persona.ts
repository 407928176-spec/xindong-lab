/** persona_extract_v0.6 前端类型（与后端 / 文档对齐） */

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  /** 允许空字符串：可与本轮 `attachment_ids` 搭配「仅附件」发送 */
  content: string;
  /** 本条用户消息携带的附件（仅前端 transcript / 气泡展示；服务端可按模型忽略额外字段） */
  attachment_ids?: string[];
}

export interface BasicInfoV06 {
  gender: string | null;
  age_or_life_stage: string | null;
  identity_role: string | null;
  location_context: string | null;
  relationship_status: string | null;
}

export interface RelationshipWithUserV06 {
  known_context: string | null;
  interaction_frequency: string | null;
  current_interaction_summary: string | null;
}

export interface ExplicitPreferencesV06 {
  likes: string[];
  dislikes: string[];
}

export interface ObservableChatStyleV06 {
  message_length: string | null;
  emoji_usage: string | null;
  initiative_pattern: string | null;
  expression_features: string[];
  typical_phrases: string[];
}

export interface VisibleLayerV06 {
  display_name: string | null;
  basic_info: BasicInfoV06;
  relationship_with_user: RelationshipWithUserV06;
  explicit_personality_notes: string[];
  explicit_interests: string[];
  explicit_preferences: ExplicitPreferencesV06;
  observable_chat_style: ObservableChatStyleV06;
  visible_background: string | null;
}

export interface PersonaExtractV06 {
  schema_version: "persona_extract_v0.6";
  visible_layer: VisibleLayerV06;
  hidden_layer: Record<string, unknown>;
}

export interface PersonaChatResponse {
  assistant_message: string;
  extract: PersonaExtractV06;
}

export interface PersonaCreatedResponse {
  id: string;
  message?: string;
}

/** POST /api/personas/confirm-generate：静默抽取后入库 */
export interface PersonaConfirmGenerateResponse {
  id: string;
  extract: PersonaExtractV06;
  message?: string;
}

export interface PersonaListItem {
  id: string;
  display_name: string;
  identity_summary: string;
  created_at: string;
  is_pinned: boolean;
  active_character_count: number;
}

/** GET /api/personas/:id */
export interface PersonaDetailResponse {
  id: string;
  display_name: string;
  created_at: string;
  visible_layer: VisibleLayerV06;
}

/** GET /api/personas/:id/delete-preview — 单个角色最小信息 */
export interface PersonaDeletePreviewItem {
  id: string;
  display_name: string;
  updated_at: string;
  ending_kind: string | null;
}

/** GET /api/personas/:id/delete-preview — 三组角色预览 */
export interface PersonaDeletePreviewResponse {
  active_in_progress: PersonaDeletePreviewItem[];
  ended_characters: PersonaDeletePreviewItem[];
  archived_characters: PersonaDeletePreviewItem[];
}
