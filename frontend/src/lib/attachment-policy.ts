/**
 * 与后端 `app/config/attachment_policy.py` 对齐：允许的 MIME + 扩展名双校验
 * （不含 gif/音视频/xlsx 等）。
 *
 * ⚠️ 这是后端策略的镜像，改这里必须同步改那边，否则会出现「前端放行、后端拒收」。
 * 前端校验只是为了即时反馈，真正说了算的是后端。
 */

/** 图片上限更严：图片要 base64 内联进模型请求体，编码后体积膨胀约 1/3。 */
export const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
/** TXT / DOCX 只在服务端解析成文本，不进请求体，可以宽松些。 */
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
export const MAX_ATTACHMENTS_PER_MESSAGE = 9;

const EXT_TO_MIME: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".txt": "text/plain",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

const ALLOWED_MIMES = new Set<string>(Object.values(EXT_TO_MIME));

export function inferMimeFromFileName(fileName: string): string {
  const lower = fileName.toLowerCase();
  const dot = lower.lastIndexOf(".");
  const ext = dot >= 0 ? lower.slice(dot) : "";
  return EXT_TO_MIME[ext] ?? "";
}

function isImageMime(mime: string): boolean {
  return mime.startsWith("image/");
}

/** 通过则返回 `null`，否则返回可读错误文案。 */
export function validateAttachmentFile(fileName: string, mimeType: string, sizeBytes: number): string | null {
  if (sizeBytes <= 0) {
    return "文件为空";
  }

  const inferred = inferMimeFromFileName(fileName);
  const mime = ((mimeType || "").trim().toLowerCase() || inferred) as string;
  if (!mime) {
    return "无法识别文件类型，请使用 jpg/png/webp/txt/docx";
  }
  if (!ALLOWED_MIMES.has(mime)) {
    return `不支持的文件类型（${mime}）。不支持 gif、音视频、Office 表格、压缩包等。`;
  }

  // 大小上限要在识别出类型之后判断：图片和文档的上限不一样。
  const limit = isImageMime(mime) ? MAX_IMAGE_BYTES : MAX_ATTACHMENT_BYTES;
  if (sizeBytes > limit) {
    const label = isImageMime(mime) ? "图片" : "单文件";
    return `${label}不能超过 ${limit / 1024 / 1024}MB`;
  }

  const lower = fileName.toLowerCase();
  const dot = lower.lastIndexOf(".");
  const ext = dot >= 0 ? lower.slice(dot) : "";
  const allowedExtsForMime = Object.entries(EXT_TO_MIME)
    .filter(([, m]) => m === mime)
    .map(([e]) => e);
  if (ext && !allowedExtsForMime.includes(ext)) {
    return `扩展名与类型不一致：${mime} 仅允许后缀 ${allowedExtsForMime.join(" / ")}`;
  }
  if (!ext) {
    return "文件名缺少扩展名";
  }

  return null;
}

/** `<input accept>` 用，收窄系统文件选择器。 */
export const ATTACHMENT_INPUT_ACCEPT =
  ".jpg,.jpeg,.png,.webp,.txt,.docx,image/jpeg,image/png,image/webp,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
