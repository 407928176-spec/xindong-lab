"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState, Fragment } from "react";

import { AttachmentPlusButton } from "@/components/ui-patterns/AttachmentPlusButton";
import { apiFetch } from "@/lib/api-client";
import {
  ATTACHMENT_INPUT_ACCEPT,
  MAX_ATTACHMENTS_PER_MESSAGE,
  inferMimeFromFileName,
  validateAttachmentFile,
} from "@/lib/attachment-policy";

interface AttachmentUploaderProps {
  scene: "persona_creation" | "character_chat";
  conversationId: string;
  draftTurnId: string;
  attachmentIds: string[];
  onAttachmentIdsChange: (ids: string[]) => void;
  disabled?: boolean;
}

/** 单条附件在本轮的展示元数据（不向服务端拉预览 URL）。 */
interface AttachmentMeta {
  displayName: string;
  mimeType: string;
  sizeBytes: number;
  previewBlobUrl?: string;
}

/** 与演示图一致：`0.06MB`（MB，两位小数）。 */
function formatAttachmentSizeMb(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(2)}MB`;
}

/** MIME → 卡片副标题用大写简称（与附件策略六种类型对齐）。 */
function mimeToAttachmentLabel(mime: string): string {
  const m = mime.trim().toLowerCase();
  switch (m) {
    case "image/jpeg":
      return "JPEG";
    case "image/png":
      return "PNG";
    case "image/webp":
      return "WEBP";
    case "text/plain":
      return "TXT";
    case "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
      return "DOCX";
    default:
      return "FILE";
  }
}

function isImageMime(mime: string): boolean {
  return mime.trim().toLowerCase().startsWith("image/");
}

function fileVisual(mime: string): { badge: string; iconClass: string } {
  const m = mime.trim().toLowerCase();
  if (m === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") {
    return { badge: "W", iconClass: "bg-blue-600 text-white" };
  }
  if (m === "text/plain") {
    return { badge: "T", iconClass: "bg-primary text-white" };
  }
  if (m.startsWith("image/")) {
    return { badge: "I", iconClass: "bg-emerald-600 text-white" };
  }
  return { badge: "F", iconClass: "bg-muted-foreground/60 text-white" };
}

function FileTypeIcon({ mime }: { mime: string }) {
  const visual = fileVisual(mime);
  return (
    <span className={`relative flex size-10 shrink-0 items-center justify-center rounded-md text-sm font-bold shadow-sm ${visual.iconClass}`}>
      <span className="absolute right-0 top-0 size-2.5 rounded-bl-sm bg-white/35" />
      {visual.badge}
    </span>
  );
}

function describeUploadStageError(stage: "upload", res?: Response, detail?: string): string {
  // 后端的 detail 已经是人话（"图片不能超过 4 MB" 之类），优先直接展示。
  if (detail) return detail;
  if (!res) return "上传失败，请检查后端服务是否在运行";
  if (res.status === 413) return "文件太大了";
  return `上传失败（HTTP ${res.status}）`;
}

/** presign → PUT OSS → complete；预览仅用 `URL.createObjectURL`，不向服务端要 signed-url。 */
export function AttachmentUploader({
  scene,
  conversationId,
  draftTurnId,
  attachmentIds,
  onAttachmentIdsChange,
  disabled = false,
}: AttachmentUploaderProps) {
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [metaById, setMetaById] = useState<Record<string, AttachmentMeta>>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const metaRef = useRef<Record<string, AttachmentMeta>>({});

  metaRef.current = metaById;

  useEffect(() => {
    return () => {
      for (const m of Object.values(metaRef.current)) {
        if (m.previewBlobUrl) URL.revokeObjectURL(m.previewBlobUrl);
      }
    };
  }, []);

  /** 父组件清空 ids（如发送成功）时撤销孤儿预览 URL，避免泄漏。 */
  useEffect(() => {
    setMetaById((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const id of Object.keys(next)) {
        if (!attachmentIds.includes(id)) {
          const row = next[id];
          if (row?.previewBlobUrl) URL.revokeObjectURL(row.previewBlobUrl);
          delete next[id];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [attachmentIds]);

  const remainingSlots = MAX_ATTACHMENTS_PER_MESSAGE - attachmentIds.length;

  function removeAttachment(id: string): void {
    setMetaById((prev) => {
      const row = prev[id];
      if (!row) return prev;
      const copy = { ...prev };
      delete copy[id];
      if (row.previewBlobUrl) URL.revokeObjectURL(row.previewBlobUrl);
      return copy;
    });
    onAttachmentIdsChange(attachmentIds.filter((x) => x !== id));
  }

  /** 附件直接 multipart 传给本地后端，由后端落盘。 */
  async function uploadOne(file: File): Promise<string> {
    const mime = (file.type || "").trim() || inferMimeFromFileName(file.name);
    const verr = validateAttachmentFile(file.name, mime, file.size);
    if (verr) {
      throw new Error(verr);
    }

    const form = new FormData();
    // 浏览器给某些文件（如 .docx）推断的 type 可能为空，用文件名兜底推断出的 mime 覆盖。
    form.append("file", new File([file], file.name, { type: mime }));
    form.append("scene", scene);
    form.append("conversation_id", conversationId);
    form.append("draft_turn_id", draftTurnId);

    let res: Response;
    try {
      res = await apiFetch("/api/attachments/upload", { method: "POST", body: form });
    } catch {
      throw new Error(describeUploadStageError("upload"));
    }

    if (!res.ok) {
      const d = (await res.json().catch(() => null)) as { detail?: unknown } | null;
      const detail = typeof d?.detail === "string" ? d.detail : undefined;
      throw new Error(describeUploadStageError("upload", res, detail));
    }

    const data = (await res.json()) as { attachment_id: string };
    return data.attachment_id;
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const raw = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (raw.length === 0 || disabled || uploading) {
      return;
    }

    setError(null);

    if (remainingSlots <= 0) {
      setError(`每条消息最多 ${MAX_ATTACHMENTS_PER_MESSAGE} 个附件`);
      return;
    }

    const picked = raw.slice(0, remainingSlots);

    setUploading(true);
    let nextIds = [...attachmentIds];
    try {
      for (const file of picked) {
        const id = await uploadOne(file);
        const mime = (file.type || "").trim() || inferMimeFromFileName(file.name);
        const previewBlobUrl = isImageMime(mime) ? URL.createObjectURL(file) : undefined;
        setMetaById((prev) => ({
          ...prev,
          [id]: {
            displayName: file.name,
            mimeType: mime,
            sizeBytes: file.size,
            previewBlobUrl,
          },
        }));
        nextIds = [...nextIds, id];
        onAttachmentIdsChange(nextIds);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        accept={ATTACHMENT_INPUT_ACCEPT}
        onChange={(ev) => void onPick(ev)}
      />
      <AttachmentPlusButton
        disabled={disabled || remainingSlots <= 0}
        uploading={uploading}
        count={attachmentIds.length}
        max={MAX_ATTACHMENTS_PER_MESSAGE}
        onClick={() => inputRef.current?.click()}
      />

      {attachmentIds.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {attachmentIds.map((id) => {
            const meta = metaById[id];
            if (!meta) return <Fragment key={id} />;

            const label = mimeToAttachmentLabel(meta.mimeType);
            const subline = `${label} ${formatAttachmentSizeMb(meta.sizeBytes)}`;
            const imgUrl = meta.previewBlobUrl;

            return (
              <div
                key={id}
                className={
                  imgUrl
                    ? "relative flex min-w-[140px] max-w-xs flex-1 flex-col gap-2 rounded-2xl bg-transparent p-1 pr-8"
                    : "relative flex min-h-[3.75rem] min-w-[220px] max-w-xs flex-1 flex-row items-center gap-3 rounded-xl bg-muted px-3 py-2 pr-9"
                }
              >
                {imgUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element -- 本地 blob 预览
                  <img
                    src={imgUrl}
                    alt=""
                    className="max-h-40 max-w-full rounded-2xl object-contain"
                  />
                ) : null}
                <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
                  <div className="truncate text-sm font-medium text-foreground" title={meta.displayName}>
                    {meta.displayName}
                  </div>
                  <div className="text-xs text-muted-foreground">{subline}</div>
                </div>
                {!imgUrl ? <FileTypeIcon mime={meta.mimeType} /> : null}
                <button
                  type="button"
                  className="bg-background/80 text-muted-foreground hover:bg-muted hover:text-foreground absolute right-1 top-1 flex size-6 items-center justify-center rounded-full border shadow-sm disabled:pointer-events-none disabled:opacity-40"
                  aria-label="移除附件"
                  disabled={disabled || uploading}
                  onClick={() => removeAttachment(id)}
                >
                  <X className="size-3.5" aria-hidden />
                </button>
              </div>
            );
          })}
        </div>
      ) : null}

      {error ? <p className="text-destructive text-xs">{error}</p> : null}
    </div>
  );
}
