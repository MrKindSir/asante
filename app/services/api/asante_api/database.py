"""Async PostgreSQL connection and request-scoped session boundary."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def database_url(database: str | None = None) -> URL:
    """Build a safely escaped Psycopg URL from Asante's environment settings."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ.get("ASANTE_POSTGRES_USER", "asante"),
        password=os.environ.get("ASANTE_POSTGRES_PASSWORD", "asante_local_dev_only"),
        host=os.environ.get("ASANTE_POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("ASANTE_POSTGRES_INTERNAL_PORT", "5432")),
        database=database or os.environ.get("ASANTE_POSTGRES_DB", "asante"),
    )


_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process engine's factory; each caller receives its own session."""
    global _engine, _sessions
    if _sessions is None:
        _engine = create_async_engine(database_url(), pool_pre_ping=True)
        _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessions


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session and always close it after use."""
    async with session_factory()() as session:
        yield session


async def dispose_database_engine() -> None:
    """Dispose the optional engine during API shutdown."""
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessions = None
