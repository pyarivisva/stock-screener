"""
Pool koneksi Redis (aioredis) khusus cache API — DB 0 (PRD §9 & §10.1).

Broker Celery memakai DB terpisah (/1, /2); cache Connector memakai DB 0.
"""

from __future__ import annotations

import logging
from redis import asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from fastapi import Request

from backend.api.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def _build_cache_url() -> str:
    """URL Redis untuk cache; paksa database index 0 kecuali REDIS_CACHE_URL override penuh."""
    settings = get_settings()
    if settings.redis_cache_url:
        return str(settings.redis_cache_url)
    auth = ""
    if settings.redis_password:
        auth = f":{settings.redis_password}@"
    return f"redis://{auth}{settings.redis_host}:{settings.redis_port}/0"


async def init_redis_pool() -> aioredis.Redis:
    """
    Inisialisasi ConnectionPool + client Redis untuk FastAPI (decode_responses=True).
    """
    global _pool
    url = _build_cache_url()
    _pool = ConnectionPool.from_url(
        url,
        max_connections=40,
        decode_responses=True,
    )
    client = aioredis.Redis(connection_pool=_pool)
    logger.info("Redis cache pool siap (URL host diparse dari konfigurasi, DB=0).")
    return client


async def close_redis_pool(redis_client: aioredis.Redis | None) -> None:
    """Tutup client dan pool."""
    global _pool
    if redis_client is not None:
        await redis_client.close()
    if _pool is not None:
        await _pool.disconnect(inuse_connections=True)
        _pool = None


def get_redis_client(request: Request) -> aioredis.Redis:
    """
    Dependency Injection: client Redis dari app.state (dibuat saat startup).
    """
    return request.app.state.redis_client
