export interface LlmConfigInput {
  base_url: string;
  api_key: string;
  model: string;
  aux_model: string;
}

export interface LlmConfigStatus {
  configured: boolean;
  base_url: string;
  model: string;
  aux_model: string;
  /** 脱敏后的 Key，仅用于回显「填过了」。后端永远不会返回明文。 */
  api_key_masked: string;
  web_search_supported: boolean;
}

export interface LlmProbeResponse {
  ok: boolean;
  message: string;
  web_search_supported: boolean;
  web_search_message: string;
  /** 实测可用的 Base URL，可能是后端自动补全 /v1 后的结果。 */
  base_url: string;
}
