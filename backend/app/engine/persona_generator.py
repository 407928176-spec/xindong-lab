"""角色 persona_prompt 生成：读取模板并调用 LLM，将 extract JSON 转化为自然语言人设提示词。"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.engine.llm_client import call_llm
from app.engine.prompts.loader import read_prompt

logger = logging.getLogger(__name__)

_MAX_PERSONA_PROMPT_CHARS = 2000


def _normalize_generated_prompt(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rewrite_shorter_persona_prompt(template: str, draft: str) -> str:
    prompt = (
        "下面这段角色人设提示词超过长度限制。请在不新增信息、不改变角色设定的前提下，"
        f"压缩到 {_MAX_PERSONA_PROMPT_CHARS} 个中文字符以内。只输出压缩后的正文。"
    )
    result = call_llm(
        messages=[
            {"role": "system", "content": template},
            {"role": "user", "content": prompt + "\n\n" + draft},
        ],
        temperature=0.3,
        stream=False,
        use_auxiliary_credentials=True,
    )
    return _normalize_generated_prompt(result)


def generate_persona_prompt(character_info: dict[str, Any]) -> str:
    """根据人设 extract_snapshot 生成写入 Character.persona_prompt 的文本。

    将 ``persona_generator_prompt.md`` 作为 system 指令，``extract_snapshot`` JSON
    作为 user 输入，调用辅助链路 LLM 生成自然语言角色人设提示词。

    若 ``extract_snapshot`` 为 None（旧库数据）或模板为空或 LLM 调用失败，
    返回空字符串，由 ``load_context`` 回退到 Persona 表拼装逻辑。
    """
    assert isinstance(character_info, dict)
    assert "persona_id" in character_info

    template = read_prompt("persona_generator_prompt.md")
    if not template:
        return ""

    extract = character_info.get("extract_snapshot")
    if not extract:
        return ""

    try:
        user_content = json.dumps(extract, ensure_ascii=False)
        result = call_llm(
            messages=[
                {"role": "system", "content": template},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
            stream=False,
            use_auxiliary_credentials=True,
        )
        text = _normalize_generated_prompt(result)
        if not text:
            return ""
        if len(text) <= _MAX_PERSONA_PROMPT_CHARS:
            return text

        rewritten = _rewrite_shorter_persona_prompt(template, text)
        if rewritten and len(rewritten) <= _MAX_PERSONA_PROMPT_CHARS:
            return rewritten
        logger.warning("generate_persona_prompt 结果超过 2000 字符，回退到表拼装")
        return ""
    except Exception:
        logger.exception("generate_persona_prompt LLM 调用失败，回退到表拼装")
        return ""
