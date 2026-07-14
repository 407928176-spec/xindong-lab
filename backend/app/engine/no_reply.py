"""角色无回应协议：<NO_REPLY> 精确匹配、流式前缀屏蔽、DB/API/LLM 上下文语义分层。"""

from __future__ import annotations

from typing import Any

from app.models.enums import MessageRole
from app.models.message import Message

NO_REPLY_TOKEN = "<NO_REPLY>"
# 仅用于「仍可能是精确 no_reply 的未完成缓冲」长度上限，防止恶意长 `<` 前缀卡死。
NO_REPLY_MAX_PREFIX_CHARS = 64
# API / 列表预览等展示层固定文案（不向用户暴露协议串）。
NO_REPLY_DISPLAY_TEXT = "对方没有回应"
# 写入 recent_messages / 摘要输入：模型可读、表示主动沉默。
NO_REPLY_LLM_PLACEHOLDER = "（角色没有回应）"


def is_exact_no_reply(raw: str) -> bool:
    """仅当整段 trim 后精确等于 <NO_REPLY> 时为 True。"""
    return (raw or "").strip() == NO_REPLY_TOKEN


def normalize_character_reply(raw: str) -> tuple[str, bool]:
    """返回 (character_reply, character_no_reply)。空模型输出不算 no_reply。"""
    if is_exact_no_reply(raw):
        return "", True
    return (raw or "").strip(), False


def _still_feasible_no_reply_buffer(buffer: str) -> bool:
    """缓冲是否仍可能最终形成「精确 no_reply」的原始串（允许 token 后仅空白）。"""
    core = buffer.lstrip()
    if not core:
        return True
    if NO_REPLY_TOKEN.startswith(core):
        return True
    if core.startswith(NO_REPLY_TOKEN):
        return core[len(NO_REPLY_TOKEN) :].strip() == ""
    return False


class NoReplyStreamSplitter:
    """流式：累积 raw；仅向下游 yield 不泄露协议串的 public 段；结束时用 raw 做唯一判定。"""

    def __init__(self) -> None:
        self._raw_parts: list[str] = []
        self._public_parts: list[str] = []
        self._buffer = ""
        self._passthrough = False

    def feed(self, chunk: str) -> list[str]:
        """返回本 chunk 对应的、可立即发给前端的文本段（可能为空或多段合并为一条）。"""
        if not chunk:
            return []
        self._raw_parts.append(chunk)
        if self._passthrough:
            self._public_parts.append(chunk)
            return [chunk]

        self._buffer += chunk

        if len(self._buffer) > NO_REPLY_MAX_PREFIX_CHARS:
            out = self._buffer
            self._public_parts.append(out)
            self._buffer = ""
            self._passthrough = True
            return [out]

        if not _still_feasible_no_reply_buffer(self._buffer):
            out = self._buffer
            self._public_parts.append(out)
            self._buffer = ""
            self._passthrough = True
            return [out]

        return []

    def finish(self) -> list[str]:
        """流结束：若整段 raw 为精确 no_reply 则不下发缓冲；否则下发剩余缓冲。"""
        raw = "".join(self._raw_parts)
        if self._passthrough:
            if self._buffer:
                self._public_parts.append(self._buffer)
                tail = self._buffer
                self._buffer = ""
                return [tail]
            return []

        if is_exact_no_reply(raw):
            self._buffer = ""
            return []

        if self._buffer:
            out = self._buffer
            self._public_parts.append(out)
            self._buffer = ""
            return [out]
        return []

    @property
    def raw_acc(self) -> str:
        return "".join(self._raw_parts)

    @property
    def public_acc(self) -> str:
        return "".join(self._public_parts)

    def normalized_reply(self) -> tuple[str, bool]:
        """与非流式共用同一套判定。"""
        return normalize_character_reply(self.raw_acc)


def recent_dict_from_message(m: Message) -> dict[str, Any]:
    """与 load_context / memory_compression 一致：沉默轮对 LLM 用占位句，并带 is_no_reply。"""
    ipc = m.internal_phase_change
    is_nr = (
        m.role == MessageRole.CHARACTER.value
        and isinstance(ipc, dict)
        and ipc.get("no_reply") is True
    )
    if is_nr:
        return {
            "role": m.role,
            "content": NO_REPLY_LLM_PLACEHOLDER,
            "is_no_reply": True,
        }
    return {"role": m.role, "content": m.content or "", "is_no_reply": False}
