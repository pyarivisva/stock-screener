import json
import logging
from math import ceil

from redis import asyncio as aioredis
import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from backend.api.cache.redis_client import get_redis_client
from backend.api.database import get_db_connection, record_to_dict
from backend.api.middleware.rate_limit import rate_limit_per_ip
from backend.api.middleware.rate_limit_api_key import rate_limit_per_api_key
from backend.api.security import verify_api_key
from backend.api.schemas import PaginationMeta, TickerMetadata, TickersResponse


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/tickers",
    tags=["tickers"],
    dependencies=[
        Depends(verify_api_key),
        Depends(rate_limit_per_api_key),
        Depends(rate_limit_per_ip),
    ],
)


@router.get("", response_model=TickersResponse)
async def get_tickers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    conn: asyncpg.Connection = Depends(get_db_connection),
    redis_client: aioredis.Redis = Depends(get_redis_client),
) -> TickersResponse:
    """
    Mengambil daftar ticker dengan pagination.
    """
    cache_key = f"tickers:all:page:{page}:size:{page_size}"
    cached = await redis_client.get(cache_key)
    if cached:
        logger.info("Cache HIT tickers: %s", cache_key)
        return TickersResponse.model_validate_json(cached)

    offset = (page - 1) * page_size
    total_records = await conn.fetchval("SELECT COUNT(*) FROM company_metadata") or 0
    rows = await conn.fetch(
        """
        SELECT ticker_id, symbol, company_name, sector, exchange, source, created_at
        FROM company_metadata
        ORDER BY symbol ASC
        LIMIT $1 OFFSET $2
        """,
        page_size,
        offset,
    )
    data = [TickerMetadata(**record_to_dict(row)) for row in rows]

    response = TickersResponse(
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_records=total_records,
            total_pages=max(1, ceil(total_records / page_size)) if page_size else 1,
        ),
        data=data,
    )
    # TTL sesuai PRD: ticker list cenderung jarang berubah.
    await redis_client.setex(cache_key, 86400, json.dumps(jsonable_encoder(response)))
    return response
