"""
Endpoint utama screener — read-through cache Redis (PRD §9.2).
"""

from __future__ import annotations

import hashlib
import json
import logging
from math import ceil

from redis import asyncio as aioredis
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from starlette import status

from backend.api.cache.redis_client import get_redis_client
from backend.api.database import get_db_connection, record_to_dict
from backend.api.middleware.rate_limit import rate_limit_per_ip
from backend.api.middleware.rate_limit_api_key import rate_limit_per_api_key
from backend.api.security import verify_api_key
from backend.api.schemas import PaginationMeta, ScreenRequest, ScreenResponse, ScreenRow

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["screen"],
    dependencies=[
        Depends(verify_api_key),
        Depends(rate_limit_per_api_key),
        Depends(rate_limit_per_ip),
    ],
)

SCREEN_CACHE_TTL_SECONDS = 3600


def build_screen_cache_key(
    ticker: str,
    date_from: object | None,
    date_to: object | None,
    indicators: list[str],
    page: int,
    page_size: int,
) -> str:
    """
    Kunci cache PRD: screen:{ticker}:{date_from}:{date_to}:{indicators_hash}
    indicators_hash merangkum daftar indikator terurut + pagination agar halaman berbeda tidak bentrok.
    """
    ind_sorted = ",".join(sorted(indicators))
    digest = hashlib.sha256(
        f"{ind_sorted}|p={page}|ps={page_size}".encode("utf-8")
    ).hexdigest()[:32]
    df = date_from.isoformat() if date_from else ""
    dt = date_to.isoformat() if date_to else ""
    return f"screen:{ticker.upper()}:{df}:{dt}:{digest}"


@router.post("/screen", response_model=ScreenResponse)
async def run_screen_query(
    payload: ScreenRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
    redis_client: aioredis.Redis = Depends(get_redis_client),
) -> ScreenResponse:
    """
    Read-through cache: cek Redis → hit return; miss → query DB → setex → return.
    """
    indicators = payload.indicators or ["ma5", "ma20", "bb_upper", "bb_lower", "stoch_k"]
    allowed = {
        "ma5",
        "ma20",
        "ma50",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "stoch_k",
        "stoch_d",
    }
    selected_indicators = [col for col in indicators if col in allowed]
    dynamic_cols = (
        ", ".join(f"si.{col}" for col in selected_indicators) if selected_indicators else ""
    )
    select_cols = "si.trade_date, si.close_price"
    if dynamic_cols:
        select_cols = f"{select_cols}, {dynamic_cols}"

    cache_key = build_screen_cache_key(
        payload.ticker,
        payload.date_from,
        payload.date_to,
        selected_indicators,
        payload.page,
        payload.page_size,
    )

    cached = await redis_client.get(cache_key)
    if cached:
        logger.info("Cache HIT screen: %s", cache_key)
        return ScreenResponse.model_validate_json(cached)

    logger.info("Cache MISS screen: %s", cache_key)

    known = await conn.fetchval(
        "SELECT 1 FROM company_metadata WHERE UPPER(symbol) = UPPER($1)",
        payload.ticker,
    )
    if not known:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticker tidak terdaftar di company_metadata (allowlist PRD §12.2).",
        )

    where_clauses = ["cm.symbol = $1"]
    params: list[object] = [payload.ticker.upper()]
    if payload.date_from:
        where_clauses.append(f"si.trade_date >= ${len(params) + 1}")
        params.append(payload.date_from)
    if payload.date_to:
        where_clauses.append(f"si.trade_date <= ${len(params) + 1}")
        params.append(payload.date_to)
    where_sql = " AND ".join(where_clauses)
    offset = (payload.page - 1) * payload.page_size

    total_records = await conn.fetchval(
        f"""
        SELECT COUNT(*)
        FROM stock_indicators si
        JOIN company_metadata cm ON cm.ticker_id = si.ticker_id
        WHERE {where_sql}
        """,
        *params,
    ) or 0

    rows = await conn.fetch(
        f"""
        SELECT {select_cols}
        FROM stock_indicators si
        JOIN company_metadata cm ON cm.ticker_id = si.ticker_id
        WHERE {where_sql}
        ORDER BY si.trade_date DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params,
        payload.page_size,
        offset,
    )
    data = [ScreenRow(**record_to_dict(row)) for row in rows]
    response = ScreenResponse(
        ticker=payload.ticker.upper(),
        pagination=PaginationMeta(
            page=payload.page,
            page_size=payload.page_size,
            total_records=total_records,
            total_pages=max(1, ceil(total_records / payload.page_size))
            if payload.page_size
            else 1,
        ),
        data=data,
    )

    await redis_client.setex(
        cache_key,
        SCREEN_CACHE_TTL_SECONDS,
        json.dumps(jsonable_encoder(response)),
    )
    return response
