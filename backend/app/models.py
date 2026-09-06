"""Shared ORM foundation; concrete table models belong to their domains."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
