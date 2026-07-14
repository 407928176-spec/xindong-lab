"""LLM 人设静默抽取 JSON 的宽松校验与归一（入库前管线）。

与严格解析 `parse_persona_extract_v06` 区分：本模块容忍模型噪声，裁剪多余字段、修复类型与枚举，
最后再 `PersonaExtractV06.model_validate`。解析或校验仍失败时 debug 日志（仅记录阶段、错误摘要、
raw 前 500 字符预览），最后才回退空白默认结构。

TODO（接线）：在写入人设数据库前由调用方执行 ``validate_and_normalize_persona_extract(llm_output)``
（例如在接入真实人设抽取推理链之后）；当前不与 ``persona_service.save_persona`` 耦合。

说明：不把「其实」单独列为污染关键词（口语常见、误杀率高）；若日后需要，再针对「她其实喜欢」等
明显推断组合单独匹配，勿扫描 typical_phrases / explicit_interests。
"""

from __future__ import annotations

import copy
import json
import logging
import math
from typing import Any

from pydantic import ValidationError

from app.schemas.persona_extract_v06 import SCHEMA_VERSION, PersonaExtractV06, default_persona_extract_v06
from app.services.persona_extract_parse import strip_json_fence

logger = logging.getLogger(__name__)

_RAW_PREVIEW_LIMIT = 500

# -----------------------------------------------------------------------------
# 契约枚举（与 docs/character_creation_extract_prompt输出格式及说明.md 对齐）
# -----------------------------------------------------------------------------

_VISIBLE_MESSAGE_LENGTH = frozenset(
    {"very_short", "short", "short_to_medium", "medium", "long", "mixed"}
)
_VISIBLE_EMOJI_USAGE = frozenset({"none", "low", "medium", "high", "mixed"})
_VISIBLE_INITIATIVE_PATTERN = frozenset(
    {"mostly_replying", "balanced", "sometimes_initiates", "often_initiates", "unclear"}
)

_HIDDEN_EMOTIONAL_EXPRESSION = frozenset(
    {"unknown", "direct", "reserved", "playful", "avoidant", "warm", "mixed"}
)
_HIDDEN_SOCIAL_OR_SELF = frozenset(
    {"unknown", "low", "medium_low", "medium", "medium_high", "high"}
)
_HIDDEN_INTIMACY_ATTITUDE = frozenset(
    {"unknown", "open", "cautious", "avoidant", "warm_slow", "mixed"}
)

_HIDDEN_PACING_TOLERANCE = frozenset(
    {"unknown", "slow", "slow_to_medium", "medium", "medium_to_fast", "fast"}
)
_HIDDEN_BOUNDARY_SENSITIVITY = frozenset(
    {"unknown", "low", "medium_low", "medium", "medium_high", "high"}
)
_HIDDEN_CONFESSION_THRESHOLD = frozenset({"unknown", "low", "medium", "high", "very_high"})

_HID_COMFORT_TRUST_RATE = frozenset({"unknown", "slow", "medium", "fast"})
_HID_INTEREST_VOLATILITY = frozenset({"unknown", "low", "medium", "high"})
_HID_ALERTNESS_TRIGGER = frozenset({"unknown", "low", "medium", "medium_high", "high"})
_HID_REPAIR_DIFFICULTY = frozenset({"unknown", "low", "medium", "high", "very_high"})
_HID_NEGATIVE_MEMORY_WEIGHT = frozenset({"unknown", "low", "medium", "high"})

# visible 污染：子串命中（不含单独「其实」，见模块 docstring）
VISIBLE_POLLUTION_KEYWORDS: tuple[str, ...] = (
    "心理侧写",
    "心理画像",
    "人格画像",
    "推断人格",
    "推断动机",
    "依恋类型",
    "依恋风格",
    "不安全依恋",
    "潜意识",
    "心智模型",
    "心智内核",
    "阴暗面",
    "人格面具",
    "人格原型",
    "人格诊断",
    "人格建模",
    "人格坐标",
    "人格光谱",
    "人格演化",
    "人格张力",
    "人格倾向",
    "人格预测",
    "人格评估",
    "依恋分型",
    "依恋推断",
    "依恋模型",
    "依恋诊断",
    "潜意识建模",
    "原型分析",
    "原型投射",
    "投射建模",
    "策略建模",
    "黑暗三角",
)

_VISIBLE_POLLUTION_SUBSTRINGS_EN: tuple[str, ...] = (
    "attachment style",
    "personality diagnosis",
)

_CN_UNKNOWN_ENUM_PHRASES = frozenset(
    {
        "未知",
        "无法判断",
        "不清楚",
        "不明确",
        "暂不掌握",
        "暂无结论",
        "尚不明确",
        "尚不清楚",
        "难以判断",
        "不好判断",
        "没法判断",
        "没法确定",
        "不确定",
    }
)


def _is_empty_marker_string(s: str) -> bool:
    """strip 后的空值别名（大小写兼容英文 null/none）。"""
    t = s.strip()
    if not t:
        return True
    tl = t.lower()
    if tl in ("null", "none", "n/a", "na"):
        return True
    return t in ("暂无", "未提及", "未知", "无法判断", "不知道", "None", "NULL")


def _raw_preview(raw_output: Any, limit: int = _RAW_PREVIEW_LIMIT) -> str:
    """用于日志：不输出完整用户侧内容，仅前若干字符。"""
    if isinstance(raw_output, str):
        text = raw_output
    elif isinstance(raw_output, dict):
        try:
            text = json.dumps(raw_output, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(raw_output)
    else:
        text = repr(raw_output)
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _normalize_nullable_string(raw: Any) -> str | None:
    """全体 string|null：None 保留；str 则 strip + 空别名 -> None；其余类型 -> None。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        t = raw.strip()
        if not t or _is_empty_marker_string(t):
            return None
        return t
    return None


def _normalize_visible_enum(raw: Any, allowed: frozenset[str]) -> str | None:
    """visible 枚举：仅 None/str；非 str 且非 None -> None；str strip 后空别名 / unknown / 中文未知 / 非法 -> None。"""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or _is_empty_marker_string(s):
        return None
    canon = s.lower().replace(" ", "_").replace("-", "_")
    if canon == "unknown":
        return None
    if s in _CN_UNKNOWN_ENUM_PHRASES:
        return None
    if canon in allowed:
        return canon
    return None


def _normalize_hidden_enum(raw: Any, allowed: frozenset[str]) -> str:
    """hidden 枚举：非 str -> unknown；str strip 后空别名 / 中文未知 / 非法 -> unknown。"""
    if not isinstance(raw, str):
        return "unknown"
    s = raw.strip()
    if not s or _is_empty_marker_string(s):
        return "unknown"
    canon = s.lower().replace(" ", "_").replace("-", "_")
    if s in _CN_UNKNOWN_ENUM_PHRASES:
        return "unknown"
    if canon in allowed:
        return canon
    return "unknown"


def _visible_meta_polluted(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    lower = s.lower()
    for frag in _VISIBLE_POLLUTION_SUBSTRINGS_EN:
        if frag in lower:
            return True
    for frag in VISIBLE_POLLUTION_KEYWORDS:
        if frag in s:
            return True
    return False


def _merge_and_prune_to_schema(payload: Any, template: Any) -> Any:
    """以 template 的 key 树为唯一允许结构：递归裁剪多余字段、补缺省、处理类型错位。"""
    if isinstance(template, dict):
        if not isinstance(payload, dict):
            return copy.deepcopy(template)
        out: dict[str, Any] = {}
        for key, tmpl_val in template.items():
            if key in payload:
                out[key] = _merge_and_prune_to_schema(payload[key], tmpl_val)
            else:
                out[key] = copy.deepcopy(tmpl_val)
        return out
    if isinstance(template, list):
        if not isinstance(payload, list):
            return []
        return list(payload)
    return payload


def _first_json_object_raw_decode(text: str) -> dict[str, Any] | None:
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _extract_dict_from_llm_raw(raw: Any) -> dict[str, Any] | None:
    """strip → strip_json_fence → json.loads；失败则对 fence 后与原始串 raw_decode 每个 ``{``。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    fenced = strip_json_fence(s)
    try:
        data = json.loads(fenced)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    for cand in (fenced, s):
        got = _first_json_object_raw_decode(cand)
        if got is not None:
            return got
    return None


def _normalize_string_list(raw: Any, max_items: int) -> list[str]:
    """仅保留非空 str；strip；空别名剔除；去重保序；截断；非 str 丢弃。"""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        t = item.strip()
        if not t or _is_empty_marker_string(t):
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_items:
            break
    return out


def _coerce_initial_hidden_scalar(raw: Any) -> int:
    default = 50
    if raw is None:
        return default
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return max(0, min(100, raw))
    if isinstance(raw, float):
        if math.isnan(raw) or math.isinf(raw):
            return default
        return max(0, min(100, int(round(raw))))
    if isinstance(raw, str):
        if _is_empty_marker_string(raw):
            return default
        try:
            x = float(raw.strip())
            if math.isnan(x) or math.isinf(x):
                return default
            return max(0, min(100, int(round(x))))
        except ValueError:
            return default
    return default


def _apply_visible_pollution(vl: dict[str, Any]) -> None:
    bi = vl.get("basic_info")
    if isinstance(bi, dict):
        for k in list(bi.keys()):
            val = bi.get(k)
            if isinstance(val, str) and _visible_meta_polluted(val):
                bi[k] = None

    ru = vl.get("relationship_with_user")
    if isinstance(ru, dict):
        for k in list(ru.keys()):
            val = ru.get(k)
            if isinstance(val, str) and _visible_meta_polluted(val):
                ru[k] = None

    epn = vl.get("explicit_personality_notes")
    if isinstance(epn, list):
        vl["explicit_personality_notes"] = [
            x for x in epn if isinstance(x, str) and x.strip() and not _visible_meta_polluted(x)
        ]

    exp = vl.get("explicit_preferences")
    if isinstance(exp, dict):
        for key in ("likes", "dislikes"):
            arr = exp.get(key)
            if isinstance(arr, list):
                exp[key] = [
                    x for x in arr if isinstance(x, str) and x.strip() and not _visible_meta_polluted(x)
                ]

    ocs = vl.get("observable_chat_style")
    if isinstance(ocs, dict):
        ef = ocs.get("expression_features")
        if isinstance(ef, list):
            ocs["expression_features"] = [
                x for x in ef if isinstance(x, str) and x.strip() and not _visible_meta_polluted(x)
            ]

    vb = vl.get("visible_background")
    if isinstance(vb, str) and _visible_meta_polluted(vb):
        vl["visible_background"] = None


def _normalize_visible_layer(vl: dict[str, Any]) -> None:
    vl["display_name"] = _normalize_nullable_string(vl.get("display_name"))

    bi = vl.get("basic_info")
    if isinstance(bi, dict):
        for k in ("gender", "age_or_life_stage", "identity_role", "location_context", "relationship_status"):
            bi[k] = _normalize_nullable_string(bi.get(k))
    ru = vl.get("relationship_with_user")
    if isinstance(ru, dict):
        for k in ("known_context", "interaction_frequency", "current_interaction_summary"):
            ru[k] = _normalize_nullable_string(ru.get(k))

    vl["explicit_personality_notes"] = _normalize_string_list(vl.get("explicit_personality_notes"), 10)
    vl["explicit_interests"] = _normalize_string_list(vl.get("explicit_interests"), 20)

    exp = vl.get("explicit_preferences")
    if isinstance(exp, dict):
        exp["likes"] = _normalize_string_list(exp.get("likes"), 20)
        exp["dislikes"] = _normalize_string_list(exp.get("dislikes"), 20)

    ocs = vl.get("observable_chat_style")
    if isinstance(ocs, dict):
        ocs["message_length"] = _normalize_visible_enum(ocs.get("message_length"), _VISIBLE_MESSAGE_LENGTH)
        ocs["emoji_usage"] = _normalize_visible_enum(ocs.get("emoji_usage"), _VISIBLE_EMOJI_USAGE)
        ocs["initiative_pattern"] = _normalize_visible_enum(
            ocs.get("initiative_pattern"), _VISIBLE_INITIATIVE_PATTERN
        )
        ocs["expression_features"] = _normalize_string_list(ocs.get("expression_features"), 15)
        ocs["typical_phrases"] = _normalize_string_list(ocs.get("typical_phrases"), 20)

    vl["visible_background"] = _normalize_nullable_string(vl.get("visible_background"))

    # 归一化 name_user_specified：宽容接受 bool / str，其余一律 False
    raw_nus = vl.get("name_user_specified")
    if isinstance(raw_nus, bool):
        vl["name_user_specified"] = raw_nus
    elif isinstance(raw_nus, str):
        vl["name_user_specified"] = raw_nus.strip().lower() in ("true", "1", "yes")
    else:
        vl["name_user_specified"] = False
    # display_name 为 null 时名字来自模型，强制 False
    if vl.get("display_name") is None:
        vl["name_user_specified"] = False

    _apply_visible_pollution(vl)

    vl["explicit_personality_notes"] = _normalize_string_list(vl.get("explicit_personality_notes"), 10)
    vl["explicit_interests"] = _normalize_string_list(vl.get("explicit_interests"), 20)
    exp = vl.get("explicit_preferences")
    if isinstance(exp, dict):
        exp["likes"] = _normalize_string_list(exp.get("likes"), 20)
        exp["dislikes"] = _normalize_string_list(exp.get("dislikes"), 20)
    ocs = vl.get("observable_chat_style")
    if isinstance(ocs, dict):
        ocs["expression_features"] = _normalize_string_list(ocs.get("expression_features"), 15)
        ocs["typical_phrases"] = _normalize_string_list(ocs.get("typical_phrases"), 20)


def _normalize_hidden_layer(hl: dict[str, Any]) -> None:
    icp = hl.get("inferred_core_profile")
    if isinstance(icp, dict):
        icp["summary"] = _normalize_nullable_string(icp.get("summary"))
        icp["profile_tags"] = _normalize_string_list(icp.get("profile_tags"), 8)
        icp["emotional_expression_style"] = _normalize_hidden_enum(
            icp.get("emotional_expression_style"), _HIDDEN_EMOTIONAL_EXPRESSION
        )
        icp["social_energy_level"] = _normalize_hidden_enum(icp.get("social_energy_level"), _HIDDEN_SOCIAL_OR_SELF)
        icp["self_protection_level"] = _normalize_hidden_enum(
            icp.get("self_protection_level"), _HIDDEN_SOCIAL_OR_SELF
        )
        icp["intimacy_attitude"] = _normalize_hidden_enum(icp.get("intimacy_attitude"), _HIDDEN_INTIMACY_ATTITUDE)

    irs = hl.get("initial_relation_state")
    if isinstance(irs, dict):
        irs["initial_relation_tendency"] = _normalize_nullable_string(irs.get("initial_relation_tendency"))
        irs["initial_impression_baseline"] = _normalize_nullable_string(irs.get("initial_impression_baseline"))
        ihs = irs.get("initial_hidden_state")
        if isinstance(ihs, dict):
            for key in ("comfort", "interest", "trust", "alertness", "baseline_compatibility"):
                ihs[key] = _coerce_initial_hidden_scalar(ihs.get(key))

    ip = hl.get("interaction_preferences")
    if isinstance(ip, dict):
        ip["positive_interaction_cues"] = _normalize_string_list(ip.get("positive_interaction_cues"), 10)
        ip["negative_interaction_cues"] = _normalize_string_list(ip.get("negative_interaction_cues"), 10)
        ip["sensitive_topics"] = _normalize_string_list(ip.get("sensitive_topics"), 10)

    pp = hl.get("pacing_profile")
    if isinstance(pp, dict):
        pp["pacing_tolerance"] = _normalize_hidden_enum(pp.get("pacing_tolerance"), _HIDDEN_PACING_TOLERANCE)
        pp["boundary_sensitivity"] = _normalize_hidden_enum(
            pp.get("boundary_sensitivity"), _HIDDEN_BOUNDARY_SENSITIVITY
        )
        pp["confession_threshold"] = _normalize_hidden_enum(
            pp.get("confession_threshold"), _HIDDEN_CONFESSION_THRESHOLD
        )

    ev = hl.get("evolution_tendency")
    if isinstance(ev, dict):
        ev["comfort_growth_rate"] = _normalize_hidden_enum(ev.get("comfort_growth_rate"), _HID_COMFORT_TRUST_RATE)
        ev["trust_growth_rate"] = _normalize_hidden_enum(ev.get("trust_growth_rate"), _HID_COMFORT_TRUST_RATE)
        ev["interest_volatility"] = _normalize_hidden_enum(ev.get("interest_volatility"), _HID_INTEREST_VOLATILITY)
        ev["alertness_trigger_level"] = _normalize_hidden_enum(
            ev.get("alertness_trigger_level"), _HID_ALERTNESS_TRIGGER
        )
        ev["repair_difficulty"] = _normalize_hidden_enum(ev.get("repair_difficulty"), _HID_REPAIR_DIFFICULTY)
        ev["negative_memory_weight"] = _normalize_hidden_enum(
            ev.get("negative_memory_weight"), _HID_NEGATIVE_MEMORY_WEIGHT
        )

    hl["distinctive_hidden_notes"] = _normalize_string_list(hl.get("distinctive_hidden_notes"), 5)


def _normalize_tree(data: dict[str, Any]) -> dict[str, Any]:
    data["schema_version"] = SCHEMA_VERSION
    vl = data.get("visible_layer")
    hl = data.get("hidden_layer")
    if isinstance(vl, dict):
        _normalize_visible_layer(vl)
    if isinstance(hl, dict):
        _normalize_hidden_layer(hl)
    return data


def validate_and_normalize_persona_extract(raw_output: Any) -> dict[str, Any]:
    """将模型输出宽松解析并归一化为 ``PersonaExtractV06`` 兼容 JSON dict。"""
    template = default_persona_extract_v06().model_dump(mode="json")

    extracted = _extract_dict_from_llm_raw(raw_output)
    json_extract_failed = extracted is None
    if extracted is None:
        extracted = {}

    if json_extract_failed:
        logger.debug(
            "persona_extract 失败 [json_extract]: %s | raw_preview=%s",
            "未能从原始输出解析出 JSON 对象（非 dict 或字符串无法解析）",
            _raw_preview(raw_output),
        )

    merged = _merge_and_prune_to_schema(extracted, template)
    if not isinstance(merged, dict):
        merged = copy.deepcopy(template)

    normalized = _normalize_tree(merged)

    try:
        model = PersonaExtractV06.model_validate(normalized)
        return model.model_dump(mode="json")
    except ValidationError as exc:
        logger.debug(
            "persona_extract 失败 [model_validate]: %s | raw_preview=%s",
            str(exc),
            _raw_preview(raw_output),
        )
        return copy.deepcopy(template)


__all__ = [
    "VISIBLE_POLLUTION_KEYWORDS",
    "validate_and_normalize_persona_extract",
    "_merge_and_prune_to_schema",
]
