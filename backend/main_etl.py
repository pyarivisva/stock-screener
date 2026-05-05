import asyncio
import logging
import os
from pathlib import Path

import pandas as pd
from urllib.parse import urlparse, urlunparse
from uuid import NAMESPACE_DNS, uuid5

from dotenv import load_dotenv

from modules.calculators.bollinger_calculator import add_bollinger_bands
from modules.calculators.ma_calculator import add_moving_averages
from modules.calculators.stochastic_calculator import add_stochastic_oscillator
from modules.fetchers.alpha_vantage_fetcher import fetch_daily_ohlcv_alpha_vantage
from modules.fetchers.merge_ohlcv_sources import merge_yfinance_and_alpha_vantage
from modules.fetchers.yfinance_fetcher import fetch_daily_ohlcv
from modules.redis_cache_invalidate import (
    invalidate_connector_caches_for_symbol,
    invalidate_ticker_list_pages,
    redis_cache_url_for_etl,
)
from modules.writers.db_writer import (
    create_pool,
    upsert_company_metadata,
    upsert_stock_indicators,
    upsert_stock_prices,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main_etl")


def build_db_url() -> str:
    """
    Menyusun DSN PostgreSQL dari variable environment.
    """

    user = os.getenv("POSTGRES_USER", "stock_user")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "stock_screener")
    if all([user, password, host, port, database]):
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    full_url = os.getenv("DATABASE_URL")
    if full_url:
        parsed = urlparse(full_url)
        if parsed.hostname == "localhost":
            normalized_netloc = f"127.0.0.1:{parsed.port or 5432}"
            if parsed.username:
                auth = parsed.username
                if parsed.password:
                    auth = f"{auth}:{parsed.password}"
                normalized_netloc = f"{auth}@{normalized_netloc}"
            return urlunparse(parsed._replace(netloc=normalized_netloc))
        return full_url

    raise ValueError("Konfigurasi database tidak ditemukan di environment.")


async def run_etl_for_ticker(pool, ticker_symbol: str) -> None:
    logger.info("=== ETL mulai untuk %s ===", ticker_symbol)

    ticker_id = str(uuid5(NAMESPACE_DNS, f"stock-screener:{ticker_symbol}"))
    av_key = (os.getenv("ALPHA_VANTAGE_API_KEY") or "").strip()

    # 1) EXTRACT (yfinance + opsional Alpha Vantage, PRD §6.1 / §7.1)
    try:
        yf_df = fetch_daily_ohlcv(ticker_symbol, period="1y", interval="1d")
        av_df = fetch_daily_ohlcv_alpha_vantage(ticker_symbol, av_key) if av_key else pd.DataFrame()
        price_df, source_meta = merge_yfinance_and_alpha_vantage(yf_df, av_df)
        if price_df.empty:
            logger.warning("Data gabungan kosong untuk %s, proses ETL dihentikan", ticker_symbol)
            return
    except Exception as exc:
        logger.exception("Tahap Extract gagal untuk %s: %s", ticker_symbol, exc)
        return

    # 2) TRANSFORM
    try:
        transformed_df = add_moving_averages(price_df)
        transformed_df = add_bollinger_bands(transformed_df)
        transformed_df = add_stochastic_oscillator(transformed_df)
        logger.info("Tahap Transform selesai untuk %s", ticker_symbol)
    except Exception as exc:
        logger.exception("Tahap Transform gagal untuk %s: %s", ticker_symbol, exc)
        return

    # 3) LOAD
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await upsert_company_metadata(
                    conn, ticker_id=ticker_id, symbol=ticker_symbol, source=source_meta
                )
                await upsert_stock_prices(conn, ticker_id=ticker_id, price_df=price_df)
                await upsert_stock_indicators(
                    conn, ticker_id=ticker_id, indicator_df=transformed_df
                )
        logger.info("Tahap Load selesai untuk %s", ticker_symbol)
    except Exception as exc:
        logger.exception("Tahap Load gagal untuk %s: %s", ticker_symbol, exc)
        return

    # 4) Invalidasi cache Connector untuk ticker ini (PRD §9.3)
    try:
        await invalidate_connector_caches_for_symbol(redis_cache_url_for_etl(), ticker_symbol)
    except Exception as exc:
        logger.warning("Invalidate Redis gagal (non-fatal) untuk %s: %s", ticker_symbol, exc)

    logger.info("=== ETL selesai untuk %s ===", ticker_symbol)


async def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    tickers = ["BBCA.JK", "TLKM.JK"]
    db_url = build_db_url()
    logger.info("Koneksi DB menuju host: %s", urlparse(db_url).hostname)
    logger.info("Memulai ETL untuk ticker: %s", ", ".join(tickers))

    pool = await create_pool(db_url)
    try:
        for ticker in tickers:
            await run_etl_for_ticker(pool, ticker)
        await invalidate_ticker_list_pages(redis_cache_url_for_etl())
    finally:
        await pool.close()
        logger.info("Koneksi database ditutup")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        logger.exception("ETL utama gagal total: %s", exc)
