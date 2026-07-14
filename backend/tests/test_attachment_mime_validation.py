"""附件上传的类型 / 大小 / 数量校验（本地存储）。"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — 注册 ORM
from app.config.attachment_policy import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_IMAGE_BYTES,
)
from app.db.base import Base
from app.services import attachment_service, local_storage_service


@pytest.fixture(autouse=True)
def _tmp_uploads(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """把上传目录指向 tmp，避免测试往仓库里写文件。"""
    monkeypatch.setattr(local_storage_service, "uploads_root", lambda: tmp_path)


def _memory_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)
    return factory()


def _upload(db: Session, *, file_name: str, mime_type: str, data: bytes, **kw):
    return attachment_service.upload_attachment(
        db,
        user_id=kw.get("user_id") or str(uuid.uuid4()),
        file_name=file_name,
        mime_type=mime_type,
        data=data,
        scene="persona_creation",
        conversation_id=kw.get("conversation_id") or str(uuid.uuid4()),
        draft_turn_id=kw.get("draft_turn_id") or str(uuid.uuid4()),
    )


def test_rejects_gif() -> None:
    with pytest.raises(ValueError, match="不支持"):
        _upload(_memory_db(), file_name="x.gif", mime_type="image/gif", data=b"x" * 100)


def test_rejects_pdf() -> None:
    with pytest.raises(ValueError, match="不支持"):
        _upload(_memory_db(), file_name="doc.pdf", mime_type="application/pdf", data=b"x" * 900)


def test_rejects_extension_mime_mismatch() -> None:
    """扩展名和 MIME 必须匹配，防止 .txt 伪装成图片绕过大小限制。"""
    with pytest.raises(ValueError, match="不匹配"):
        _upload(_memory_db(), file_name="x.txt", mime_type="image/png", data=b"x" * 10)


def test_rejects_oversize_image() -> None:
    """图片上限更严：要 base64 内联进模型请求体。"""
    with pytest.raises(ValueError, match="图片不能超过"):
        _upload(
            _memory_db(),
            file_name="x.jpg",
            mime_type="image/jpeg",
            data=b"x" * (MAX_IMAGE_BYTES + 1),
        )


def test_rejects_oversize_file() -> None:
    with pytest.raises(ValueError, match="文件不能超过"):
        _upload(
            _memory_db(),
            file_name="x.txt",
            mime_type="text/plain",
            data=b"x" * (MAX_ATTACHMENT_BYTES + 1),
        )


def test_rejects_empty_file() -> None:
    with pytest.raises(ValueError, match="文件为空"):
        _upload(_memory_db(), file_name="x.txt", mime_type="text/plain", data=b"")


def test_txt_larger_than_image_cap_is_allowed() -> None:
    """TXT 只在服务端解析成文本、不进请求体，所以允许超过图片上限。"""
    row = _upload(
        _memory_db(),
        file_name="big.txt",
        mime_type="text/plain",
        data=b"x" * (MAX_IMAGE_BYTES + 1),
    )
    assert row.status == "uploaded"


def test_upload_persists_file_and_row() -> None:
    db = _memory_db()
    row = _upload(db, file_name="a.png", mime_type="image/png", data=b"\x89PNG-data")

    assert row.status == "uploaded"
    assert row.size == len(b"\x89PNG-data")
    assert row.storage_provider == "local"
    # 落盘内容必须能原样读回来——这是图片 base64 链路的前提。
    assert local_storage_service.read_bytes(row.object_key) == b"\x89PNG-data"


def test_enforces_per_turn_attachment_limit() -> None:
    db = _memory_db()
    uid, conv, turn = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for i in range(MAX_ATTACHMENTS_PER_MESSAGE):
        _upload(
            db,
            file_name=f"{i}.png",
            mime_type="image/png",
            data=b"d",
            user_id=uid,
            conversation_id=conv,
            draft_turn_id=turn,
        )
    with pytest.raises(ValueError, match="不能超过"):
        _upload(
            db,
            file_name="overflow.png",
            mime_type="image/png",
            data=b"d",
            user_id=uid,
            conversation_id=conv,
            draft_turn_id=turn,
        )
