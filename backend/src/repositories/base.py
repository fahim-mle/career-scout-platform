"""Shared repository utilities for async SQLAlchemy repositories."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseRepository(Generic[ModelT]):
    """Base repository with common DB helpers and error handling."""

    def __init__(self, db: AsyncSession, model_type: type[ModelT]):
        """Initialize repository with session and model class.

        Args:
            db: Active asynchronous SQLAlchemy session.
            model_type: ORM model class for this repository.
        """
        self.db = db
        self.model_type = model_type

    async def _commit_and_refresh(self, entity: ModelT) -> ModelT:
        """Commit transaction and refresh the ORM entity.

        Args:
            entity: Entity to refresh after commit.

        Returns:
            The refreshed entity.

        """
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def _rollback_safely(self) -> None:
        """Attempt rollback and preserve the original error context."""
        try:
            await self.db.rollback()
        except SQLAlchemyError as exc:
            logger.bind(
                repository=self.__class__.__name__,
                model=self.model_type.__name__,
                error=str(exc),
            ).error("Rollback failed")

    def _list_with_pagination(self, items: Sequence[ModelT]) -> list[ModelT]:
        """Normalize sequence results to list type.

        Args:
            items: Sequence returned by SQLAlchemy scalars collection.

        Returns:
            Materialized list of model instances.
        """
        return list(items)
