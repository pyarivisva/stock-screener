import logging
from typing import Iterable

import asyncpg
import pandas as pd


logger = logging.getLogger(__name__)


async def create_pool(db_url: str) -> asyncpg.Pool:
    """
    Membuat pool koneksi asyncpg agar siap dipakai worker ETL.
    """
    return await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=10)


async def upsert_company_metadata(
    conn: asyncpg.Connection, ticker_id: str, symbol: str, source: str = "yfinance"
) -> None:
    """
    Upsert metadata ticker minimum agar relasi FK valid.
    """
    query = """
        INSERT INTO company_metadata (ticker_id, symbol, company_name, sector, exchange, source, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (symbol) DO UPDATE
        SET source = EXCLUDED.source
    """
    # Placeholder sederhana untuk data awal; bisa diperkaya dari fetcher metadata.
    await conn.execute(query, ticker_id, symbol, symbol, None, "IDX", source)


async def upsert_stock_prices(
    conn: asyncpg.Connection, ticker_id: str, price_df: pd.DataFrame
) -> None:
    """
    Upsert data OHLCV ke tabel stock_prices.
    """
    if price_df.empty:
        logger.warning("price_df kosong, lewati upsert stock_prices")
        return

    query = """
        INSERT INTO stock_prices
        (ticker_id, trade_date, open_price, high_price, low_price, close_price, volume, source, ingested_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (ticker_id, trade_date) DO UPDATE
        SET open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume,
            source = EXCLUDED.source,
            ingested_at = EXCLUDED.ingested_at
    """

    records: Iterable[tuple] = (
        (
            ticker_id,
            row.trade_date,
            float(row.open_price),
            float(row.high_price),
            float(row.low_price),
            float(row.close_price),
            int(row.volume),
            row.source,
            row.ingested_at,
        )
        for row in price_df.itertuples(index=False)
    )
    await conn.executemany(query, records)
    logger.info("Upsert stock_prices selesai: %s baris", len(price_df))


async def upsert_stock_indicators(
    conn: asyncpg.Connection, ticker_id: str, indicator_df: pd.DataFrame
) -> None:
    """
    Upsert data indikator precomputed ke tabel stock_indicators.
    """
    if indicator_df.empty:
        logger.warning("indicator_df kosong, lewati upsert stock_indicators")
        return

    query = """
        INSERT INTO stock_indicators
        (ticker_id, trade_date, close_price, ma5, ma20, ma50, bb_upper, bb_middle, bb_lower, bb_width, stoch_k, stoch_d, computed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
        ON CONFLICT (ticker_id, trade_date) DO UPDATE
        SET close_price = EXCLUDED.close_price,
            ma5 = EXCLUDED.ma5,
            ma20 = EXCLUDED.ma20,
            ma50 = EXCLUDED.ma50,
            bb_upper = EXCLUDED.bb_upper,
            bb_middle = EXCLUDED.bb_middle,
            bb_lower = EXCLUDED.bb_lower,
            bb_width = EXCLUDED.bb_width,
            stoch_k = EXCLUDED.stoch_k,
            stoch_d = EXCLUDED.stoch_d,
            computed_at = NOW()
    """

    def to_nullable_float(value):
        return None if pd.isna(value) else float(value)

    records: Iterable[tuple] = (
        (
            ticker_id,
            row.trade_date,
            float(row.close_price),
            to_nullable_float(row.ma5),
            to_nullable_float(row.ma20),
            to_nullable_float(row.ma50),
            to_nullable_float(row.bb_upper),
            to_nullable_float(row.bb_middle),
            to_nullable_float(row.bb_lower),
            to_nullable_float(row.bb_width),
            to_nullable_float(row.stoch_k),
            to_nullable_float(row.stoch_d),
        )
        for row in indicator_df.itertuples(index=False)
    )
    await conn.executemany(query, records)
    logger.info("Upsert stock_indicators selesai: %s baris", len(indicator_df))
