/** 与后端 `schemas/character.py` 对齐的类型（阶段 4） */

export type CharacterMessageRole = "user" | "character";

export interface CharacterMessageItem {
  id: string;
  role: CharacterMessageRole;
  content: string;
  round_number: number;
  created_at: string;
  is_no_reply?: boolean;
  message_type?: "normal" | "no_reply";
  display_text?: string;
  /** 用户消息关联的附件 ID（展示用；下载地址另调 signed-urls） */
  attachment_ids?: string[];
}

export interface CharacterListItem {
  id: string;
  display_name: string;
  persona_id: string;
  persona_display_name: string;
  heartbeat_score: number;
  status: string;
  last_message_preview: string;
  updated_at: string;
  is_pinned: boolean;
  ending?: { result: string; evaluation: string; user_review?: string | null } | null;
}

export interface CharacterDetailResponse {
  id: string;
  display_name: string;
  persona_id: string;
  persona_display_name: string;
  heartbeat_score: number;
  status: string;
  messages: CharacterMessageItem[];
  ending: { result: string; evaluation: string; user_review?: string | null } | null;
}

export interface CharacterCreatedResponse {
  id: string;
  persona_id: string;
  display_name: string;
  heartbeat_score: number;
  message: string;
}

export interface CharacterChatResponse {
  assistant_message: string;
  user_message: CharacterMessageItem;
  assistant_message_item: CharacterMessageItem;
  heartbeat_score: number;
  round: number;
  ending: { result: string; evaluation: string; user_review?: string | null } | null;
  assistant_no_reply?: boolean;
  assistant_display_text?: string;
  assistant_message_type?: "normal" | "no_reply";
}
