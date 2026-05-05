import json
import logging
from datetime import date
from math import ceil

from redis import asyncio as aioredis
import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder

from backend.api.cache.redis_client import get_redis_client
from backend.api.config import get_settings
from backend.api.database import get_db_connection, record_to_dict
from backend.api.middleware.rate_limit import rate_limit_per_ip
from backend.api.middleware.rate_limit_api_key import rate_limit_per_api_key
from backend.api.security import verify_api_key
from backend.api.schemas import HistoricalStockResponse, PaginationMeta, StockPrice


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/stocks",
    tags=["stocks"],
    dependencies=[
        Depends(verify_api_key),
        Depends(rate_limit_per_api_key),
        Depends(rate_limit_per_ip),
    ],
)


@router.get("/{symbol}/historical", response_model=HistoricalStockResponse)
async def get_historical_prices(
    symbol: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    conn: asyncpg.Connection = Depends(get_db_connection),
    redis_client: aioredis.Redis = Depends(get_redis_client),
) -> HistoricalStockResponse:
    """
    Mengambil data historis OHLCV dengan pagination.
    Endpoint ini di-cache di Redis karena sering dipanggil berulang.
    """
    settings = get_settings()
    cache_key = f"stocks:{symbol}:{date_from}:{date_to}:{page}:{page_size}"

    cached = await redis_client.get(cache_key)
    if cached:
        logger.info("Cache HIT historical: %s", cache_key)
        return HistoricalStockResponse.model_validate_json(cached)

    logger.info("Cache MISS historical: %s", cache_key)
    where_clauses = ["cm.symbol = $1"]
    params: list[object] = [symbol.upper()]

    if date_from:
        where_clauses.append(f"sp.trade_date >= ${len(params) + 1}")
        params.append(date_from)
    if date_to:
        where_clauses.append(f"sp.trade_date <= ${len(params) + 1}")
        params.append(date_to)

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM stock_prices sp
        JOIN company_metadata cm ON cm.ticker_id = sp.ticker_id
        WHERE {where_sql}
    """
    total_records = await conn.fetchval(count_query, *params) or 0

    data_query = f"""
        SELECT
            cm.symbol,
            sp.trade_date,
            sp.open_price,
            sp.high_price,
            sp.low_price,
            sp.close_price,
            sp.volume,
            sp.source,
            sp.ingested_at
        FROM stock_prices sp
        JOIN company_metadata cm ON cm.ticker_id = sp.ticker_id
        WHERE {where_sql}
        ORDER BY sp.trade_date DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """
    rows = await conn.fetch(data_query, *params, page_size, offset)
    data = [StockPrice(**record_to_dict(row)) for row in rows]

    response = HistoricalStockResponse(
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_records=total_records,
            total_pages=max(1, ceil(total_records / page_size)) if page_size else 1,
        ),
        data=data,
    )

    await redis_client.setex(
        cache_key,
        settings.redis_ttl_historical,
        json.dumps(jsonable_encoder(response)),
    )
    return response
