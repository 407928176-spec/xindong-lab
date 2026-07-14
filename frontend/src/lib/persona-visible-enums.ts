/** observable_chat_style 枚举 → 中文展示名 */

export const MESSAGE_LENGTH_LABELS: Record<string, string> = {
  very_short: "非常简短",
  short: "偏短",
  short_to_medium: "短句为主，偶尔展开",
  medium: "中等长度",
  long: "经常长段表达",
  mixed: "长短不固定",
};

export const EMOJI_USAGE_LABELS: Record<string, string> = {
  none: "基本不用",
  low: "较少使用",
  medium: "偶尔使用",
  high: "经常使用",
  mixed: "使用不固定",
};

export const INITIATIVE_PATTERN_LABELS: Record<string, string> = {
  mostly_replying: "回应为主",
  balanced: "双方接近",
  sometimes_initiates: "偶尔主动",
  often_initiates: "经常主动",
};
