"""附件 MIME / 大小策略。

⚠️ 前端有一份镜像：``frontend/src/lib/attachment-policy.ts``。改这里请同步改那边，
否则会出现「前端放行、后端拒收」的割裂体验。
"""

from __future__ import annotations

# 图片（送入模型：读本地文件 → base64 data URI → image_url）
MODEL_IMAGE_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

# 非图片附件（TXT / DOCX：服务端解析为文本后送入 Chat）
MODEL_FILE_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

MODEL_ATTACHMENT_ALLOWED_MIME_TYPES: frozenset[str] = (
    MODEL_IMAGE_ALLOWED_MIME_TYPES | MODEL_FILE_ALLOWED_MIME_TYPES
)

MIME_TO_SUFFIX: dict[str, frozenset[str]] = {
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/png": frozenset({".png"}),
    "image/webp": frozenset({".webp"}),
    "text/plain": frozenset({".txt"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset({".docx"}),
}

# 图片上限比普通文件严：图片要 base64 内联进模型请求体，编码后体积膨胀约 1/3，
# 4MB 的图片编码完约 5.5MB，再叠加人设和历史对话已经接近不少供应商的请求体上限。
MAX_IMAGE_BYTES = 4 * 1024 * 1024
# TXT / DOCX 只在服务端解析成文本，不进请求体，可以宽松些。
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

MAX_ATTACHMENTS_PER_MESSAGE = 9

# TXT/DOCX 提取与总量限制
MAX_EXTRACTED_TEXT_PER_ATTACHMENT = 10_000
MAX_EXTRACTED_TEXT_COMBINED = 30_000
MAX_DOCX_PARAGRAPHS = 300
