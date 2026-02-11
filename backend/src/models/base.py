"""SQLAlchemy declarative base classes."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Root declarative base for all ORM models."""

    pass


class BaseModel(Base):
    """Base model with common primary key and timestamps."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["Base", "BaseModel"]
