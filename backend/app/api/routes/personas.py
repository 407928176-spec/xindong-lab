"""人设相关路由：人设创建对话（``character_creation_chat_prompt``）；静默抽取并入库见 ``POST /personas/confirm-generate``。

人设静默抽取：``character_creation_extract_prompt.md`` + 辅助模型。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_id_streaming, get_db
from app.models.user import User
from app.schemas.persona import (
    PersonaChatRequest,
    PersonaChatResponse,
    PersonaConfirmGenerateRequest,
    PersonaConfirmGenerateResponse,
    PersonaCreatedResponse,
    PersonaDeletePreviewResponse,
    PersonaDetailResponse,
    PersonaListItem,
    PersonaSaveRequest,
    PinToggleResponse,
)
from app.services import persona_service

router = APIRouter(prefix="/personas", tags=["personas"])


@router.post("/chat/stream")
def persona_chat_stream(
    payload: PersonaChatRequest,
    current_user_id: str = Depends(get_current_user_id_streaming),
) -> StreamingResponse:
    """SSE：流式推送人设创建助手 token；末帧 ``type:done`` 含完整 ``assistant_message`` 与 mock ``extract``。"""
    return StreamingResponse(
        persona_service.iter_persona_chat_sse_lines(payload, user_id=current_user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=PersonaChatResponse)
def persona_chat(
    payload: PersonaChatRequest,
    current_user: User = Depends(get_current_user),
) -> PersonaChatResponse:
    """对话式创建人设：返回智能体文本与可见层预览（字段分离）；助手正文走 LLM。"""
    try:
        return persona_service.handle_persona_chat(payload, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/confirm-generate",
    response_model=PersonaConfirmGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def persona_confirm_generate(
    payload: PersonaConfirmGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonaConfirmGenerateResponse:
    """静默抽取 persona_extract JSON 并入库。"""
    try:
        return persona_service.confirm_generate_persona(
            db,
            payload,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("", response_model=PersonaCreatedResponse, status_code=status.HTTP_201_CREATED)
def persona_create(
    payload: PersonaSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonaCreatedResponse:
    """保存人设到数据库（兼容路径：客户端自带 extract）。"""
    try:
        return persona_service.save_persona(db, payload, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[PersonaListItem])
def persona_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PersonaListItem]:
    """人设库列表。"""
    return persona_service.list_personas(db, user_id=current_user.id)


@router.get("/archive", response_model=list[PersonaListItem])
def persona_archive_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PersonaListItem]:
    """人设回收站列表：已删除的人设。"""
    return persona_service.list_archived_personas(db, user_id=current_user.id)


@router.delete("/archive")
def persona_archive_clear(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """清空人设回收站：永久删除所有已软删除的人设及其关联角色。"""
    deleted_count = persona_service.clear_archived_personas(db, user_id=current_user.id)
    return {"deleted_count": deleted_count}


@router.get("/{persona_id}", response_model=PersonaDetailResponse)
def persona_detail(
    persona_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonaDetailResponse:
    """单人设详情：可见层（extract_snapshot 优先）。"""
    detail = persona_service.get_persona_detail(db, persona_id, user_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人设不存在")
    return detail


@router.post("/{persona_id}/pin", response_model=PinToggleResponse)
def persona_pin_toggle(
    persona_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PinToggleResponse:
    """切换人设置顶状态。"""
    try:
        is_pinned = persona_service.toggle_pin_persona(db, persona_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PinToggleResponse(is_pinned=is_pinned)


@router.get("/{persona_id}/delete-preview", response_model=PersonaDeletePreviewResponse)
def persona_delete_preview(
    persona_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonaDeletePreviewResponse:
    """返回删除该人设会影响的三组角色：进行中（会阻挡）、已结局（会被一并清除）、回收站（会物理删除）。"""
    try:
        return persona_service.get_persona_characters_summary(db, persona_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/{persona_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def persona_delete(
    persona_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """软删除人设：先检查是否有未删除的关联角色。"""
    try:
        persona_service.delete_persona(db, persona_id, user_id=current_user.id)
    except ValueError as exc:
        msg = str(exc)
        http_status = (
            status.HTTP_409_CONFLICT
            if "还有角色聊天" in msg
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=http_status, detail=msg) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{persona_id}/restore", response_model=PersonaDetailResponse)
def persona_restore(
    persona_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PersonaDetailResponse:
    """恢复已删除人设。"""
    try:
        persona_service.restore_persona(db, persona_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    detail = persona_service.get_persona_detail(db, persona_id, user_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="人设不存在")
    return detail


@router.delete(
    "/{persona_id}/permanently",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def persona_permanently_delete(
    persona_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """永久删除人设。"""
    try:
        persona_service.permanently_delete_persona(db, persona_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
