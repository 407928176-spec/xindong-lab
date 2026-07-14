"""从 `prompts/` 目录按文件名读取 UTF-8 文本，供各节点统一加载 prompt。"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def read_prompt(filename: str) -> str:
    """读取 `backend/app/engine/prompts/{filename}` 全文；文件不存在返回空串。"""
    path = _PROMPTS_DIR / filename
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()
