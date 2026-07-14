"""与持久化字段对应的枚举，全部用稳定字符串值，便于迁移到 PostgreSQL。"""

from __future__ import annotations

from enum import StrEnum


class PersonaCreationMethod(StrEnum):
    """人设创建方式，对应 PRD 三种入口。"""

    AI_AUTO = "ai_auto"
    CHAT_UPLOAD = "chat_upload"
    TEXT_DESCRIPTION = "text_description"


class CharacterStatus(StrEnum):
    """角色关系线状态，对应首页卡片标签。"""

    IN_PROGRESS = "in_progress"
    # 终局已触发但用户尚未打开聊天查看；仍显示在首页并标记终局徽章
    ENDING_UNREAD = "ending_unread"
    ENDED = "ended"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    """消息发送方。"""

    USER = "user"
    CHARACTER = "character"


class LoveSignalMark(StrEnum):
    """表白识别标记；阶段 2 仅占位，阶段 5 前后由对话链路写入。"""

    NONE = "none"
    LIGHT_EXPRESSION = "light_expression"
    EXPLICIT_RELATIONSHIP = "explicit_relationship"


class ReviewType(StrEnum):
    """复盘类型。"""

    SHORT = "short"
    LONG = "long"


class EndingKind(StrEnum):
    """终局类型，对应 PRD 终局三种来源的粗分类。"""

    CONFESSION_SUCCESS = "confession_success"
    CONFESSION_FAIL_CONTINUE = "confession_fail_continue"
    CONFESSION_FAIL_TERMINAL = "confession_fail_terminal"
    USER_ARCHIVED = "user_archived"


class AttachmentScene(StrEnum):
    """附件业务场景（OSS object_key 路径段）。"""

    PERSONA_CREATION = "persona_creation"
    CHARACTER_CHAT = "character_chat"


class AttachmentStatus(StrEnum):
    """附件存储状态。"""

    PENDING = "pending"
    UPLOADED = "uploaded"
    FAILED = "failed"
    DELETED = "deleted"


class AttachmentStorageProvider(StrEnum):
    """附件存储方式。开源版把附件存在玩家自己的硬盘上。"""

    LOCAL = "local"
