"""Compatibility entrypoint for Docker and local uvicorn."""

from src.main import app, create_app

__all__ = ["app", "create_app"]
