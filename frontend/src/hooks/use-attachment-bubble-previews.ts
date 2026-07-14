"use client";

import { useEffect, useMemo, useState } from "react";

import type { AttachmentBubblePreview } from "@/components/attachments/MessageAttachmentCapsules";
import { apiFetch } from "@/lib/api-client";
import { getApiBaseUrl } from "@/lib/api-base";

/**
 * 汇总对话里用户消息的 attachment_ids，批量拉元信息，供气泡胶囊展示。
 *
 * 附件存在本机，内容直接由 `/api/attachments/{id}/content` 提供，不需要签名 URL；
 * 这里只批量取文件名和 MIME 用来决定怎么渲染。
 *
 * 使用 AbortController：快速连续切换 messages（乐观更新）时取消过时请求。
 */
export function useAttachmentBubblePreviews(flatAttachmentIds: string[]): Record<
  string,
  AttachmentBubblePreview | undefined
> {
  const [previewById, setPreviewById] = useState<
    Record<string, AttachmentBubblePreview | undefined>
  >({});

  const idsKey = useMemo(
    () => JSON.stringify([...new Set(flatAttachmentIds)].sort()),
    [flatAttachmentIds],
  );

  useEffect(() => {
    const uniqueSorted = JSON.parse(idsKey) as string[];
    if (uniqueSorted.length === 0) {
      setPreviewById({});
      return;
    }

    const ac = new AbortController();

    void (async () => {
      try {
        const res = await apiFetch("/api/attachments/meta", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ attachment_ids: uniqueSorted }),
          signal: ac.signal,
        });
        if (!res.ok) {
          return;
        }
        const data = (await res.json()) as {
          items: Array<{
            attachment_id: string;
            mime_type?: string;
            file_name?: string;
          }>;
        };
        const base = getApiBaseUrl();
        const map: Record<string, AttachmentBubblePreview> = {};
        for (const it of data.items) {
          map[it.attachment_id] = {
            contentUrl: `${base}/api/attachments/${it.attachment_id}/content`,
            mimeType: it.mime_type ?? "",
            fileName: it.file_name ?? "",
          };
        }
        if (!ac.signal.aborted) {
          setPreviewById(map);
        }
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") {
          return;
        }
      }
    })();

    return () => ac.abort();
  }, [idsKey]);

  return previewById;
}
