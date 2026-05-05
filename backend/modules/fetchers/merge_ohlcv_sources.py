"""
Gabungan dual-source yfinance + Alpha Vantage (PRD §7.1).

Jika kedua sumber punya baris untuk tanggal yang sama dan harga berbeda material,
log peringatan dan **utamakan nilai Alpha Vantage** (sumber berlisensi).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

_REL_CLOSE_EPS = 1e-4  # 0.01% relatif untuk deteksi diskrepansi


def merge_yfinance_and_alpha_vantage(
    yf_df: pd.DataFrame,
    av_df: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    """
    Mengembalikan (dataframe OHLCV terurut naik per trade_date, sumber_metadata).

    sumber_metadata: 'alpha_vantage' | 'yfinance' | 'dual_source'
    """
    if av_df is None or av_df.empty:
        return yf_df.copy() if yf_df is not None else pd.DataFrame(), "yfinance"
    if yf_df is None or yf_df.empty:
        logger.warning("yfinance kosong; memakai hanya Alpha Vantage.")
        out = av_df.copy().sort_values("trade_date").reset_index(drop=True)
        return out, "alpha_vantage"

    yf_i = yf_df.set_index("trade_date").sort_index()
    av_i = av_df.set_index("trade_date").sort_index()
    all_dates = sorted(set(yf_i.index) | set(av_i.index))
    now = datetime.now(timezone.utc)
    out_rows: list[dict] = []

    for d in all_dates:
        in_yf = d in yf_i.index
        in_av = d in av_i.index
        if in_yf and in_av:
            yrow = yf_i.loc[d]
            arow = av_i.loc[d]
            if isinstance(yrow, pd.DataFrame):
                yrow = yrow.iloc[0]
            if isinstance(arow, pd.DataFrame):
                arow = arow.iloc[0]
            yc = float(yrow["close_price"])
            ac = float(arow["close_price"])
            denom = max(abs(yc), 1e-9)
            if abs(yc - ac) / denom > _REL_CLOSE_EPS:
                logger.warning(
                    "Diskrepansi OHLCV %s: close yfinance=%s alpha_vantage=%s → pakai Alpha Vantage.",
                    d,
                    yc,
                    ac,
                )
            ser = arow
            source = "alpha_vantage"
        elif in_av:
            ser = av_i.loc[d]
            if isinstance(ser, pd.DataFrame):
                ser = ser.iloc[0]
            source = "alpha_vantage"
        else:
            ser = yf_i.loc[d]
            if isinstance(ser, pd.DataFrame):
                ser = ser.iloc[0]
            source = "yfinance"

        out_rows.append(
            {
                "trade_date": d,
                "open_price": float(ser["open_price"]),
                "high_price": float(ser["high_price"]),
                "low_price": float(ser["low_price"]),
                "close_price": float(ser["close_price"]),
                "volume": int(ser["volume"]),
                "source": source,
                "ingested_at": now,
            }
        )

    out = pd.DataFrame(out_rows).sort_values("trade_date").reset_index(drop=True)
    sources = {r["source"] for r in out_rows}
    if sources == {"alpha_vantage"}:
        meta = "alpha_vantage"
    elif sources == {"yfinance"}:
        meta = "yfinance"
    else:
        meta = "dual_source"
    return out, meta
