"""
Rate limiting berbasis Redis per IP (PRD §11.3, pola kunci §9.2).

Maksimal 60 request per menit per IP; melebihi → HTTP 429.
"""

from __future__ import annotations

import time

from redis import asyncio as aioredis
from fastapi import Depends, HTTPException, Request
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from backend.api.cache.redis_client import get_redis_client

# Batas sesuai PRD §11.3 (token bucket disederhanakan jadi fixed window per menit)
MAX_REQUESTS_PER_MINUTE = 60


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def rate_limit_per_ip(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis_client),
) -> None:
    """
    Dependency FastAPI: increment counter Redis per menit per IP.
    """
    ip = _client_ip(request)
    minute_bucket = int(time.time() // 60)
    key = f"ratelimit:{ip}:{minute_bucket}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)

    if count > MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Batas {MAX_REQUESTS_PER_MINUTE} request per menit tercapai. Coba lagi nanti.",
        )
