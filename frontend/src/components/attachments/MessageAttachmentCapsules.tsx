"use client";

import { ExternalLink, FileText, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

export interface AttachmentBubblePreview {
  contentUrl: string;
  mimeType: string;
  fileName: string;
}

interface MessageAttachmentCapsulesProps {
  attachmentIds: string[];
  previewById: Record<string, AttachmentBubblePreview | undefined>;
  onImageLoad?: () => void;
}

function isImageMime(mime: string): boolean {
  return mime.trim().toLowerCase().startsWith("image/");
}

function isTextMime(mime: string): boolean {
  return mime.trim().toLowerCase() === "text/plain";
}

function attachmentLabel(p: AttachmentBubblePreview | undefined, fallback: string): string {
  return (p?.fileName || "").trim() || fallback;
}

function fileVisual(mime: string): { badge: string; label: string; iconClass: string } {
  const m = mime.trim().toLowerCase();
  if (m === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") {
    return { badge: "W", label: "DOCX", iconClass: "bg-blue-600 text-white" };
  }
  if (m === "text/plain") {
    return { badge: "T", label: "TXT", iconClass: "bg-primary text-white" };
  }
  if (m.startsWith("image/")) {
    return { badge: "I", label: m.split("/")[1]?.toUpperCase() || "IMG", iconClass: "bg-emerald-600 text-white" };
  }
  return { badge: "F", label: "FILE", iconClass: "bg-muted-foreground/60 text-white" };
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

function AttachmentPreviewDialog({
  item,
  onClose,
}: {
  item: AttachmentBubblePreview;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [loadingText, setLoadingText] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const image = isImageMime(item.mimeType);
  const textFile = isTextMime(item.mimeType);
  const title = attachmentLabel(item, "附件预览");

  useEffect(() => {
    if (!textFile) return;
    const ac = new AbortController();
    setLoadingText(true);
    setTextError(null);

    void fetch(item.contentUrl, { signal: ac.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((body) => setText(body))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setTextError(e instanceof Error ? e.message : "文本预览加载失败");
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoadingText(false);
      });

    return () => ac.abort();
  }, [item.contentUrl, textFile]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="bg-background flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{title}</p>
            <p className="text-muted-foreground text-xs">{item.mimeType || "未知类型"}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <a
              href={item.contentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground inline-flex size-8 items-center justify-center rounded-md border"
              aria-label="在新标签打开"
              title="在新标签打开"
            >
              <ExternalLink className="size-4" aria-hidden />
            </a>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground inline-flex size-8 items-center justify-center rounded-md border"
              onClick={onClose}
              aria-label="关闭预览"
              title="关闭预览"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        </div>

        <div className="flex min-h-[18rem] flex-1 items-center justify-center overflow-auto bg-muted/20 p-4">
          {image ? (
            // eslint-disable-next-line @next/next/no-img-element -- 附件由本地后端提供，非 Next 可优化的静态资源。
            <img
              src={item.contentUrl}
              alt={title}
              className="max-h-[72vh] max-w-full rounded-lg object-contain"
            />
          ) : textFile ? (
            <div className="bg-background w-full self-stretch overflow-auto rounded-lg border p-4">
              {loadingText ? (
                <div className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                  正在加载文本预览
                </div>
              ) : textError ? (
                <p className="text-destructive text-sm">{textError}</p>
              ) : (
                <pre className="whitespace-pre-wrap break-words text-sm leading-relaxed">{text}</pre>
              )}
            </div>
          ) : (
            <div className="bg-background flex max-w-md flex-col items-center gap-3 rounded-lg border p-6 text-center">
              <FileText className="text-muted-foreground size-10" aria-hidden />
              <div>
                <p className="font-medium">{title}</p>
                <p className="text-muted-foreground mt-1 text-sm">
                  当前类型暂不支持站内正文预览，可在新标签打开查看。
                </p>
              </div>
              <a
                href={item.contentUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary inline-flex items-center gap-1 text-sm font-medium"
              >
                在新标签打开
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function MessageAttachmentCapsules({
  attachmentIds,
  previewById,
  onImageLoad,
}: MessageAttachmentCapsulesProps) {
  const [previewing, setPreviewing] = useState<AttachmentBubblePreview | null>(null);

  if (attachmentIds.length === 0) {
    return null;
  }

  return (
    <>
      <div className="mt-2 flex flex-wrap gap-2">
        {attachmentIds.map((id, i) => {
          const p = previewById[id];
          const label = attachmentLabel(p, `附件 ${i + 1}`);

          if (!p) {
            return (
              <span
                key={id}
                className="bg-muted/70 text-muted-foreground inline-flex max-w-[220px] items-center gap-2 rounded-lg border px-2.5 py-1 text-xs"
              >
                <span className="truncate">{label}</span>
                <span className="shrink-0 opacity-70">加载中</span>
              </span>
            );
          }

          const showImage = isImageMime(p.mimeType);
          const visual = fileVisual(p.mimeType);

          return (
            <button
              key={id}
              type="button"
              className={
                showImage
                  ? "flex max-w-[240px] flex-col gap-1 rounded-2xl bg-transparent p-0 text-left text-xs transition-opacity hover:opacity-90"
                  : "inline-flex min-w-[220px] max-w-[280px] items-center gap-3 rounded-xl bg-muted px-3 py-2 text-left transition-colors hover:bg-muted/80"
              }
              title={label}
              onClick={() => setPreviewing(p)}
            >
              {showImage ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element -- 附件由本地后端提供，非 Next 可优化的静态资源。 */}
                  <img
                    src={p.contentUrl}
                    alt={label}
                    className="max-h-48 max-w-full rounded-2xl object-contain"
                    onLoad={onImageLoad}
                  />
                  <span className="sr-only">{label}</span>
                </>
              ) : (
                <>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{visual.label}</p>
                  </div>
                  <FileTypeIcon mime={p.mimeType} />
                </>
              )}
            </button>
          );
        })}
      </div>

      {previewing ? (
        <AttachmentPreviewDialog item={previewing} onClose={() => setPreviewing(null)} />
      ) : null}
    </>
  );
}
