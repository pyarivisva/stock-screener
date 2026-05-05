import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


logger = logging.getLogger(__name__)


def fetch_daily_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Mengambil data OHLCV harian dari yfinance.
    """
    try:
        logger.info("Mulai fetch data yfinance untuk ticker=%s", ticker)
        raw_df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
        )

        if raw_df.empty:
            logger.warning("Data kosong dari yfinance untuk ticker=%s", ticker)
            return pd.DataFrame()

        # Pada yfinance versi tertentu, kolom bisa berbentuk MultiIndex:
        # (Open, BBCA.JK), (Close, BBCA.JK), dst.
        if isinstance(raw_df.columns, pd.MultiIndex):
            raw_df.columns = raw_df.columns.get_level_values(0)

        # Normalisasi nama kolom agar konsisten untuk proses transform.
        df = raw_df.copy()
        df.columns = [str(col).lower() for col in df.columns]
        df = df.rename(
            columns={
                "open": "open_price",
                "high": "high_price",
                "low": "low_price",
                "close": "close_price",
                "volume": "volume",
            }
        )

        # Pastikan kolom tanggal konsisten bernama trade_date.
        df.index.name = "trade_date"
        df = df.reset_index()
        if "trade_date" not in df.columns:
            # Fallback jika index name dari provider bukan trade_date.
            first_col = df.columns[0]
            df = df.rename(columns={first_col: "trade_date"})
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df["source"] = "yfinance"
        # Timestamptz di PostgreSQL membutuhkan timestamp timezone-aware.
        df["ingested_at"] = datetime.now(timezone.utc)

        selected_cols = [
            "trade_date",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "source",
            "ingested_at",
        ]
        missing_cols = [col for col in selected_cols if col not in df.columns]
        if missing_cols:
            logger.error("Kolom wajib tidak tersedia untuk ticker=%s: %s", ticker, missing_cols)
            return pd.DataFrame()

        df = df[selected_cols].dropna(subset=["trade_date", "close_price"])
        logger.info("Selesai fetch %s baris untuk ticker=%s", len(df), ticker)
        return df
    except Exception as exc:
        logger.exception("Gagal fetch data yfinance ticker=%s: %s", ticker, exc)
        return pd.DataFrame()
