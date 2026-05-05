from math import ceil

import asyncpg
from fastapi import APIRouter, Depends

from backend.api.database import get_db_connection, record_to_dict
from backend.api.middleware.rate_limit import rate_limit_per_ip
from backend.api.middleware.rate_limit_api_key import rate_limit_per_api_key
from backend.api.security import verify_api_key
from backend.api.schemas import PaginationMeta, ScreenerRequest, ScreenerResponse, ScreenerResult


router = APIRouter(
    prefix="/screener",
    tags=["screener"],
    dependencies=[
        Depends(verify_api_key),
        Depends(rate_limit_per_api_key),
        Depends(rate_limit_per_ip),
    ],
)


@router.post("/ma-cross", response_model=ScreenerResponse)
async def screen_ma_cross(
    payload: ScreenerRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ScreenerResponse:
    """
    Screener sederhana: cari saham dengan MA5 > MA20.
    """
    where_clauses = ["si.ma5 IS NOT NULL", "si.ma20 IS NOT NULL", "si.ma5 > si.ma20"]
    params: list[object] = []

    if payload.date_from:
        where_clauses.append(f"si.trade_date >= ${len(params) + 1}")
        params.append(payload.date_from)
    if payload.date_to:
        where_clauses.append(f"si.trade_date <= ${len(params) + 1}")
        params.append(payload.date_to)
    if payload.min_stoch_k is not None:
        where_clauses.append(f"si.stoch_k >= ${len(params) + 1}")
        params.append(payload.min_stoch_k)

    where_sql = " AND ".join(where_clauses)
    offset = (payload.page - 1) * payload.page_size

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM stock_indicators si
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
            si.stoch_k
        FROM stock_indicators si
        JOIN company_metadata cm ON cm.ticker_id = si.ticker_id
        WHERE {where_sql}
        ORDER BY si.trade_date DESC, cm.symbol ASC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
    """
    rows = await conn.fetch(data_query, *params, payload.page_size, offset)
    data = [ScreenerResult(**record_to_dict(row)) for row in rows]

    return ScreenerResponse(
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
