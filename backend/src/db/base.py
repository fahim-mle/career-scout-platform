"""Database metadata and model imports for migrations."""

from src.models.base import Base
# Import all models here so Alembic can detect them
# from src.models import application, job, match_score, profile  # noqa: F401

__all__ = ["Base"]
