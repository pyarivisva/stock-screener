"""
Slice B4b — fetch OHLCV harian dari Alpha Vantage (PRD §6.1, §7.1).

Free tier membatasi ~25 request/hari; jika rate limit / error, kembalikan DataFrame kosong.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_ENDPOINT = "https://www.alphavantage.co/query"


def fetch_daily_ohlcv_alpha_vantage(symbol: str, api_key: str) -> pd.DataFrame:
    """
    Ambil seri harian TIME_SERIES_DAILY dan normalisasi ke skema yang sama dengan yfinance_fetcher.
    """
    key = (api_key or "").strip()
    if not key:
        return pd.DataFrame()

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol.strip(),
        "apikey": key,
        "outputsize": "full",
    }
    try:
        resp = requests.get(ALPHA_VANTAGE_ENDPOINT, params=params, timeout=90)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("Alpha Vantage request gagal untuk %s: %s", symbol, exc)
        return pd.DataFrame()

    if "Note" in payload or "Information" in payload:
        logger.warning(
            "Alpha Vantage rate limit / info message untuk %s: %s",
            symbol,
            payload.get("Note") or payload.get("Information"),
        )
        return pd.DataFrame()

    if "Error Message" in payload:
        logger.warning("Alpha Vantage error untuk %s: %s", symbol, payload["Error Message"])
        return pd.DataFrame()

    series = payload.get("Time Series (Daily)")
    if not series or not isinstance(series, dict):
        logger.warning("Alpha Vantage tidak mengembalikan Time Series (Daily) untuk %s", symbol)
        return pd.DataFrame()

    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for date_str, ohlcv in series.items():
        try:
            trade_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        try:
            rows.append(
                {
                    "trade_date": trade_date,
                    "open_price": float(ohlcv.get("1. open", 0) or 0),
                    "high_price": float(ohlcv.get("2. high", 0) or 0),
                    "low_price": float(ohlcv.get("3. low", 0) or 0),
                    "close_price": float(ohlcv.get("4. close", 0) or 0),
                    "volume": int(float(ohlcv.get("5. volume", 0) or 0)),
                    "source": "alpha_vantage",
                    "ingested_at": now,
                }
            )
        except (TypeError, ValueError):
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values("trade_date").reset_index(drop=True)
    logger.info("Alpha Vantage: %s baris untuk %s", len(df), symbol)
    return df
