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
from backend.api.schemas import (
    IndicatorsResponse,
    LatestIndicatorResponse,
    PaginationMeta,
    TechnicalIndicators,
)


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/indicators",
    tags=["indicators"],
    dependencies=[
        Depends(verify_api_key),
        Depends(rate_limit_per_api_key),
        Depends(rate_limit_per_ip),
    ],
)


@router.get("/{symbol}", response_model=IndicatorsResponse)
async def get_technical_indicators(
    symbol: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    conn: asyncpg.Connection = Depends(get_db_connection),
    redis_client: aioredis.Redis = Depends(get_redis_client),
) -> IndicatorsResponse:
    """
    Mengambil data indikator teknikal pre-computed per ticker.
    """
    symbol = symbol.strip().upper()
    settings = get_settings()
    cache_key = f"indicators:{symbol}:{date_from}:{date_to}:{page}:{page_size}"

    cached = await redis_client.get(cache_key)
    if cached:
        logger.info("Cache HIT indicators: %s", cache_key)
        return IndicatorsResponse.model_validate_json(cached)

    where_clauses = ["cm.symbol = $1"]
    params: list[object] = [symbol]
    if date_from:
        where_clauses.append(f"si.trade_date >= ${len(params) + 1}")
        params.append(date_from)
    if date_to:
        where_clauses.append(f"si.trade_date <= ${len(params) + 1}")
        params.append(date_to)
    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM stock_indicators si
        JOIN company_metadata cm ON cm.ticker_id = si.ticker_id
        WHERE {where_sql}
    """
    total_records = await conn.fetchval(count_query, *params) or 0

    data_query = f"""
        SELECT
            cm.symbol,
            si.trade_date,
            si.close_price,
            si.ma5,
            si.ma20,
            si.ma50,
            si.bb_upper,
            si.bb_middle,
            si.bb_lower,
            si.bb_width,
            si.stoch_k,
            si.stoch_d,
            si.computed_at
        FROM stock_indicators si
        JOIN company_metadata cm ON cm.ticker_id = si.ticker_id
        WHERE {where_sql}
        ORDER BY si.trade_date DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """
    rows = await conn.fetch(data_query, *params, page_size, offset)
    data = [TechnicalIndicators(**record_to_dict(row)) for row in rows]

    response = IndicatorsResponse(
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
        settings.redis_ttl_indicators,
        json.dumps(jsonable_encoder(response)),
    )
    return response


@router.get("/{symbol}/latest", response_model=LatestIndicatorResponse)
async def get_latest_indicator(
    symbol: str,
    conn: asyncpg.Connection = Depends(get_db_connection),
    redis_client: aioredis.Redis = Depends(get_redis_client),
) -> LatestIndicatorResponse:
    """
    Mengambil baris indikator terbaru untuk satu ticker.
    """
    symbol = symbol.strip().upper()
    cache_key = f"latest:{symbol}"
    cached = await redis_client.get(cache_key)
    if cached:
        logger.info("Cache HIT latest indicator: %s", cache_key)
        return LatestIndicatorResponse.model_validate_json(cached)

    row = await conn.fetchrow(
        """
        SELECT
            cm.symbol,
            si.trade_date,
            si.close_price,
            si.ma5,
            si.ma20,
            si.ma50,
            si.bb_upper,
            si.bb_middle,
            si.bb_lower,
            si.bb_width,
            si.stoch_k,
            si.stoch_d,
            si.computed_at
        FROM stock_indicators si
        JOIN company_metadata cm ON cm.ticker_id = si.ticker_id
        WHERE cm.symbol = $1
        ORDER BY si.trade_date DESC
        LIMIT 1
        """,
        symbol,
    )

    response = LatestIndicatorResponse(
        data=TechnicalIndicators(**record_to_dict(row)) if row else None
    )
    await redis_client.setex(cache_key, 300, json.dumps(jsonable_encoder(response)))
    return response
