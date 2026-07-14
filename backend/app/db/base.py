"""ORM 声明式基类。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有模型的统一基类，便于 `metadata.create_all` 一次性建表。"""
