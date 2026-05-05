import logging
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
from fastapi import Request

from backend.api.config import get_settings


logger = logging.getLogger(__name__)


async def init_database_pool() -> asyncpg.Pool:
    """
    Inisialisasi pool koneksi asyncpg untuk endpoint API.
    """
    settings = get_settings()
    return await asyncpg.create_pool(
        dsn=settings.resolved_database_url,
        min_size=10,
        max_size=50,
    )


async def close_database_pool(pool: asyncpg.Pool | None) -> None:
    if pool:
        await pool.close()


async def get_db_connection(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Dependency Injection koneksi DB per-request.
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        yield connection


def record_to_dict(record: asyncpg.Record) -> dict[str, Any]:
    """
    Konversi asyncpg.Record ke dict biasa.
    """
    return dict(record.items())
