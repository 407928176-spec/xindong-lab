"""附件：本地上传与读取。

存对象存储时需要三步（预签名 → 客户端直传 → 确认）；存本地硬盘后压缩成一步。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config.attachment_policy import MAX_ATTACHMENT_BYTES
from app.models.user import User
from app.schemas.attachment import (
    AttachmentMetaItem,
    AttachmentMetaResponse,
    UploadAttachmentResponse,
)
from app.services import attachment_service as attach_svc

router = APIRouter(prefix="/attachments", tags=["attachments"])

_DETAIL_ATTACHMENTS_DB = (
    "数据库未就绪或缺少 attachments 表。请在 backend 目录执行 python scripts/init_db.py"
)


@router.post("/upload", response_model=UploadAttachmentResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    scene: str = Form(...),
    conversation_id: str = Form(...),
    draft_turn_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadAttachmentResponse:
    """上传一个附件。校验通过后直接落到 backend/data/uploads/ 并建记录。"""
    # 先按上限截断读取：不能因为有人 POST 一个 2GB 的文件就把内存吃光。
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB",
        )

    try:
        row = attach_svc.upload_attachment(
            db,
            user_id=current_user.id,
            file_name=(file.filename or "").strip(),
            mime_type=(file.content_type or "").strip(),
            data=data,
            scene=scene.strip(),
            conversation_id=conversation_id.strip(),
            draft_turn_id=draft_turn_id.strip(),
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_DETAIL_ATTACHMENTS_DB,
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return UploadAttachmentResponse(
        attachment_id=row.id,
        file_name=row.file_name,
        mime_type=row.mime_type,
        size=row.size,
        status=row.status,
    )


@router.get("/{attachment_id}/content")
def get_attachment_content(
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """返回附件原文件，供前端预览缩略图。"""
    try:
        row, data = attach_svc.read_attachment_bytes(
            db,
            user_id=current_user.id,
            attachment_id=attachment_id.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return Response(
        content=data,
        media_type=row.mime_type or "application/octet-stream",
        headers={
            # 附件内容不可变（object_key 含随机 UUID，改图必换 key），可以放心长缓存。
            "Cache-Control": "private, max-age=31536000, immutable",
            # 强制下载语义，避免上传的 txt/html 在同源下被当页面渲染。
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/meta", response_model=AttachmentMetaResponse)
def get_attachments_meta(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentMetaResponse:
    """批量取附件元信息，供历史消息渲染附件胶囊。"""
    ids = body.get("attachment_ids") or []
    if not isinstance(ids, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="attachment_ids 必须是数组")

    items: list[AttachmentMetaItem] = []
    for aid in ids[:50]:
        try:
            row = attach_svc.get_attachment_for_user(
                db,
                user_id=current_user.id,
                attachment_id=str(aid).strip(),
            )
        except (ValueError, PermissionError):
            # 单个附件读不到不该让整条历史消息渲染失败，跳过即可。
            continue
        items.append(
            AttachmentMetaItem(
                attachment_id=row.id,
                file_name=row.file_name or "",
                mime_type=row.mime_type or "",
                size=row.size or 0,
            )
        )
    return AttachmentMetaResponse(items=items)
