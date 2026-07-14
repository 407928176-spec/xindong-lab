"""解析人设静默抽取模型输出的 JSON（persona_extract_v0.6）。"""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.schemas.persona_extract_v06 import PersonaExtractV06


def strip_json_fence(raw: str) -> str:
    """去除可选 Markdown 代码围栏，逻辑与 evaluate_state 一致。"""
    s = raw.strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if not lines:
        return ""
    lines = lines[1:]
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_persona_extract_v06(raw: str) -> PersonaExtractV06:
    """将模型原始字符串解析为校验后的根模型。"""
    stripped = strip_json_fence(raw)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ValueError(f"抽取 JSON 解析失败: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("抽取 JSON 根节点必须是对象")
    try:
        return PersonaExtractV06.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"抽取 JSON 字段校验失败: {e}") from e
