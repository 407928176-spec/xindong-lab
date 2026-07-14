"""ORM 模型聚合：确保导入 side-effect 注册到 Base.metadata。"""

from app.models.attachment import Attachment
from app.models.character import Character
from app.models.ending import Ending
from app.models.message import Message
from app.models.persona import Persona
from app.models.review import Review
from app.models.user import User

__all__ = [
    "Persona",
    "Character",
    "Message",
    "Attachment",
    "Review",
    "Ending",
    "User",
]
