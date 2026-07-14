"""附件本地存储：把上传的文件存在玩家自己的硬盘上。

开源版没有对象存储。所有附件落在 ``backend/data/uploads/`` 下，路径结构：

    uploads/<scene>/<conversation_id>/<draft_turn_id>/<uuid>.<ext>

``object_key`` 沿用「相对 uploads 根目录的 POSIX 相对路径」这个概念，字段名和数据库
结构都不用改；只是它现在指向本地文件而不是 OSS 对象。

**安全**：``object_key`` 会参与拼接真实文件路径，所以必须严防路径穿越——玩家自己
的机器上风险有限，但这份代码是公开的，别人可能把它部署到服务器上。
:func:`validate_object_key_strict` 因此做了双重保证：先做字符级检查，再用
``Path.resolve()`` 确认最终路径确实落在 uploads 根目录内。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import unquote

# object_key 的合法字符：只允许 UUID / 场景名 / 文件后缀会用到的字符。
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_EXPECTED_SEGMENTS = 4  # scene / conversation_id / draft_turn_id / filename


def uploads_root() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    root = backend_root / "data" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def generate_object_key(
    *,
    scene: str,
    conversation_id: str,
    draft_turn_id: str,
    file_suffix: str,
) -> str:
    """生成一个新的 object_key。文件名用随机 UUID，不使用玩家提供的原始文件名。"""
    suffix = file_suffix if file_suffix.startswith(".") else f".{file_suffix}"
    return f"{scene}/{conversation_id}/{draft_turn_id}/{uuid.uuid4()}{suffix}"


def validate_object_key_strict(
    object_key: str,
    *,
    scene: str,
    conversation_id: str,
    draft_turn_id: str | None = None,
) -> None:
    """校验 object_key 合法且与数据库记录一致。不合法直接抛 ValueError。"""
    key = (object_key or "").strip()
    if not key:
        raise ValueError("object_key 为空")
    # 反斜杠在 Windows 上是路径分隔符；URL 编码可以绕过朴素的 ".." 检查，先解码再查。
    if "\\" in key or ".." in key or ".." in unquote(key):
        raise ValueError("object_key 非法")
    if key.startswith("/"):
        raise ValueError("object_key 不能是绝对路径")

    segments = key.split("/")
    if len(segments) != _EXPECTED_SEGMENTS:
        raise ValueError("object_key 结构不正确")
    for seg in segments:
        if not seg or not _SAFE_SEGMENT_RE.match(seg):
            raise ValueError("object_key 含非法字符")

    if segments[0] != scene:
        raise ValueError("object_key 的 scene 与记录不一致")
    if segments[1] != conversation_id:
        raise ValueError("object_key 的 conversation 与记录不一致")
    if draft_turn_id and segments[2] != draft_turn_id:
        raise ValueError("object_key 的 draft_turn 与记录不一致")


def abs_path(object_key: str) -> Path:
    """object_key → 绝对路径。

    即使 :func:`validate_object_key_strict` 已经查过一遍，这里仍然用 resolve() 再确认
    一次最终路径没有逃出 uploads 根目录——纵深防御，成本几乎为零。
    """
    root = uploads_root().resolve()
    path = (root / object_key).resolve()
    if not path.is_relative_to(root):
        raise ValueError("object_key 越界")
    return path


def save_bytes(object_key: str, data: bytes) -> int:
    """写入文件，返回实际写入字节数。"""
    path = abs_path(object_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def read_bytes(object_key: str) -> bytes:
    path = abs_path(object_key)
    if not path.is_file():
        raise ValueError("附件文件不存在")
    return path.read_bytes()


def exists(object_key: str) -> bool:
    try:
        return abs_path(object_key).is_file()
    except ValueError:
        return False


def delete(object_key: str) -> None:
    """删除文件。文件本来就不存在时静默返回。"""
    try:
        path = abs_path(object_key)
    except ValueError:
        return
    path.unlink(missing_ok=True)
