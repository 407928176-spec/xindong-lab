"""角色与角色对话路由：阶段 4 走普通 FastAPI 路由 + ORM，mock 回复。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_id_streaming, get_db
from app.models.user import User
from app.schemas.character import (
    CharacterChatRequest,
    CharacterChatResponse,
    CharacterCreateRequest,
    CharacterCreatedResponse,
    CharacterDetailResponse,
    CharacterListItem,
    PinToggleResponse,
)
from app.services.character_service import (
    CharacterChatBusyError,
    CharacterChatEndedError,
    CharacterPersistenceError,
    chat_with_character,
)
from app.services import character_service

router = APIRouter(prefix="/characters", tags=["characters"])


@router.post("", response_model=CharacterCreatedResponse, status_code=status.HTTP_201_CREATED)
def character_create(
    payload: CharacterCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterCreatedResponse:
    try:
        return character_service.create_character(db, payload, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[CharacterListItem])
def character_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CharacterListItem]:
    return character_service.list_characters(db, user_id=current_user.id)


@router.get("/archive", response_model=list[CharacterListItem])
def character_archive_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CharacterListItem]:
    """角色回收站列表：已删除的角色。"""
    return character_service.list_archived_characters(db, user_id=current_user.id)


@router.delete("/archive")
def character_archive_clear(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """清空角色回收站：永久删除所有已软删除的角色。"""
    deleted_count = character_service.clear_archived_characters(db, user_id=current_user.id)
    return {"deleted_count": deleted_count}


@router.get("/ended", response_model=list[CharacterListItem])
def character_ended_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CharacterListItem]:
    """缘散录列表：已到达终局的角色。"""
    return character_service.list_ended_characters(db, user_id=current_user.id)


@router.get("/{character_id}", response_model=CharacterDetailResponse)
def character_detail(
    character_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterDetailResponse:
    detail = character_service.get_character_detail(db, character_id, user_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return detail


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def character_delete(
    character_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除角色及其对话消息等（级联由数据库外键保证）。"""
    try:
        character_service.delete_character(db, character_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{character_id}/acknowledge-ending", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def character_acknowledge_ending(
    character_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """用户打开终局聊天后调用：将卡片从首页的终局待读状态移入缘散录。"""
    try:
        character_service.acknowledge_ending(db, character_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{character_id}/pin", response_model=PinToggleResponse)
def character_pin_toggle(
    character_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PinToggleResponse:
    """切换角色置顶状态。"""
    try:
        is_pinned = character_service.toggle_pin_character(db, character_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PinToggleResponse(is_pinned=is_pinned)


@router.post("/{character_id}/chat", response_model=CharacterChatResponse)
def character_chat(
    character_id: str,
    payload: CharacterChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterChatResponse:
    try:
        result = chat_with_character(
            db,
            character_id,
            payload,
            background_tasks,
            user_id=current_user.id,
        )
    except CharacterChatBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    except CharacterChatEndedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CharacterPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return result


@router.post("/{character_id}/chat/stream")
def character_chat_stream(
    character_id: str,
    payload: CharacterChatRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id_streaming),
) -> StreamingResponse:
    """SSE：先流式推送角色回复 token，最后一条 `type:done` 与 `POST /chat` JSON 对齐。"""
    return StreamingResponse(
        character_service.iter_character_chat_sse_lines(
            character_id,
            payload,
            background_tasks,
            user_id=current_user_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{character_id}/restore", response_model=CharacterDetailResponse)
def character_restore(
    character_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CharacterDetailResponse:
    """恢复已删除角色。"""
    try:
        character_service.restore_character(db, character_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    detail = character_service.get_character_detail(db, character_id, user_id=current_user.id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return detail


@router.delete(
    "/{character_id}/permanently",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def character_permanently_delete(
    character_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """永久删除角色。"""
    try:
        character_service.permanently_delete_character(db, character_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
