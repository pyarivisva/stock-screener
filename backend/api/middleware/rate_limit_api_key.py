"""
Rate limiting per API key (header X-API-Key) — PRD §11.3.

Menggunakan fixed window per menit di Redis (sama pola dengan rate_limit_per_ip).
"""

from __future__ import annotations

import hashlib
import time

from redis import asyncio as aioredis
from fastapi import Depends, HTTPException, Request
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from backend.api.cache.redis_client import get_redis_client

MAX_REQUESTS_PER_MINUTE_PER_KEY = 60


async def rate_limit_per_api_key(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis_client),
) -> None:
    raw = (request.headers.get("X-API-Key") or "").strip()
    if not raw:
        return
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    minute_bucket = int(time.time() // 60)
    key = f"ratelimit:apikey:{digest}:{minute_bucket}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)

    if count > MAX_REQUESTS_PER_MINUTE_PER_KEY:
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Batas {MAX_REQUESTS_PER_MINUTE_PER_KEY} request per menit per API key "
                "tercapai. Coba lagi nanti."
            ),
        )
