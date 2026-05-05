"""
Streamlit UI — Phase 5 Frontend Layer (PRD §7.1–7.2).
Slice F1: form filter di sidebar.
Slice F2: chart interaktif + tabel validasi (tanpa komputasi indikator di UI).
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots

# Muat .env dari root project (PRD §12.4 — secret tidak di-hardcode)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# Base URL Connector API (bisa override lewat env untuk Docker/host lain)
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _api_headers() -> dict[str, str]:
    """Header X-API-Key untuk endpoint yang dilindungi (PRD §12.1)."""
    key = (os.getenv("API_SECRET_KEY") or "").strip()
    if not key:
        return {}
    return {"X-API-Key": key}


FALLBACK_TICKERS = ["BBCA.JK", "TLKM.JK"]


@st.cache_data(ttl=120, show_spinner=False)
def fetch_ticker_symbols() -> list[str]:
    """Daftar `symbol` dari GET /api/v1/tickers untuk dropdown."""
    url = f"{API_BASE}/api/v1/tickers"
    params = {"page": 1, "page_size": 500}
    resp = requests.get(url, params=params, headers=_api_headers(), timeout=30)
    resp.raise_for_status()
    body = resp.json()
    symbols = sorted({row["symbol"] for row in body.get("data", []) if row.get("symbol")})
    return symbols if symbols else list(FALLBACK_TICKERS)


def build_indicator_columns(
    *,
    ma5: bool,
    ma20: bool,
    ma50: bool,
    bollinger: bool,
    stoch_k: bool,
    stoch_d: bool,
) -> list[str]:
    """Susun daftar kolom untuk POST /screen sesuai pilihan pengguna (PRD: MA / BB / Stochastic)."""
    out: list[str] = []
    if ma5:
        out.append("ma5")
    if ma20:
        out.append("ma20")
    if ma50:
        out.append("ma50")
    if bollinger:
        out.extend(["bb_upper", "bb_middle", "bb_lower"])
    if stoch_k:
        out.append("stoch_k")
    if stoch_d:
        out.append("stoch_d")
    return out


def fetch_screen(
    ticker: str,
    date_from: date | None,
    date_to: date | None,
    indicators: list[str],
    page_size: int = 500,
) -> dict:
    """Memanggil endpoint utama PRD: POST /api/v1/screen."""
    url = f"{API_BASE}/api/v1/screen"
    payload = {
        "ticker": ticker.strip().upper(),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "indicators": indicators,
        "page": 1,
        "page_size": min(page_size, 500),
    }
    resp = requests.post(url, json=payload, headers=_api_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_historical_ohlcv(
    ticker: str,
    date_from: date | None,
    date_to: date | None,
    page_size: int = 500,
) -> list[dict]:
    """
    Mengambil OHLCV untuk candlestick.
    Response /screen tidak memuat open/high/low/volume; PRD F2 membutuhkan candlestick,
    jadi kita gabungkan dengan GET /api/v1/stocks/{symbol}/historical.
    """
    params: dict[str, str | int] = {"page": 1, "page_size": min(page_size, 500)}
    if date_from:
        params["date_from"] = date_from.isoformat()
    if date_to:
        params["date_to"] = date_to.isoformat()
    sym = quote(ticker.strip(), safe="")
    url = f"{API_BASE}/api/v1/stocks/{sym}/historical"
    resp = requests.get(url, params=params, headers=_api_headers(), timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return body.get("data", [])


def build_chart_df(screen_rows: list[dict], ohlcv_rows: list[dict]) -> pd.DataFrame:
    """Gabungkan baris indikator (screen) dengan OHLCV berdasarkan trade_date."""
    df_ind = pd.DataFrame(screen_rows)
    if df_ind.empty:
        return pd.DataFrame()
    df_ind["trade_date"] = pd.to_datetime(df_ind["trade_date"]).dt.normalize()

    df_ohlc = pd.DataFrame(ohlcv_rows)
    if df_ohlc.empty:
        return df_ind.sort_values("trade_date")
    df_ohlc["trade_date"] = pd.to_datetime(df_ohlc["trade_date"]).dt.normalize()

    keep_ohlc = [
        "trade_date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
    ]
    df_ohlc = df_ohlc[[c for c in keep_ohlc if c in df_ohlc.columns]]

    # Hindari duplikat close: candlestick memakai close dari OHLCV; indikator join tanpa close ganda
    ind_cols = [c for c in df_ind.columns if c != "trade_date" and c != "close_price"]
    df_ind_only = df_ind[["trade_date"] + [c for c in ind_cols if c in df_ind.columns]]
    merged = df_ohlc.merge(df_ind_only, on="trade_date", how="inner")
    return merged.sort_values("trade_date").reset_index(drop=True)


def make_figure(df: pd.DataFrame, selected_indicators: list[str]) -> go.Figure:
    """Candlestick + garis indikator yang dipilih; Stochastic di sumbu Y sekunder (skala 0–100)."""
    has_stoch = (
        ("stoch_k" in selected_indicators and "stoch_k" in df.columns)
        or ("stoch_d" in selected_indicators and "stoch_d" in df.columns)
    )
    fig = make_subplots(specs=[[{"secondary_y": bool(has_stoch)}]])

    fig.add_trace(
        go.Candlestick(
            x=df["trade_date"],
            open=df["open_price"],
            high=df["high_price"],
            low=df["low_price"],
            close=df["close_price"],
            name="OHLCV",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        secondary_y=False,
    )

    colors = {
        "ma5": "#2196f3",
        "ma20": "#ff9800",
        "bb_upper": "#9c27b0",
        "bb_lower": "#9c27b0",
        "bb_middle": "#607d8b",
        "ma50": "#4caf50",
        "stoch_d": "#00bcd4",
    }

    stoch_cols = {"stoch_k", "stoch_d"}
    for col in selected_indicators:
        if col not in df.columns or col in stoch_cols:
            continue
        fig.add_trace(
            go.Scatter(
                x=df["trade_date"],
                y=df[col],
                mode="lines",
                name=col.replace("_", " ").upper(),
                line=dict(width=1.5, color=colors.get(col, "#888888")),
            ),
            secondary_y=False,
        )

    if "stoch_k" in selected_indicators and "stoch_k" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["trade_date"],
                y=df["stoch_k"],
                mode="lines",
                name="STOCH %K",
                line=dict(width=1.5, color=colors.get("stoch_k", "#e91e63")),
            ),
            secondary_y=True,
        )
    if "stoch_d" in selected_indicators and "stoch_d" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["trade_date"],
                y=df["stoch_d"],
                mode="lines",
                name="STOCH %D",
                line=dict(width=1.5, color=colors.get("stoch_d", "#00bcd4")),
            ),
            secondary_y=True,
        )

    fig.update_layout(
        title="Harga & indikator (data pre-computed dari API)",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=640,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=48, r=48, t=80, b=48),
    )
    fig.update_yaxes(title_text="Harga", secondary_y=False)
    if has_stoch:
        fig.update_yaxes(title_text="Stochastic (0–100)", secondary_y=True, range=[0, 100])
    return fig


def main() -> None:
    st.set_page_config(
        page_title="Stock Screener",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("Stock Screener")
    st.caption("Frontend Streamlit — Form (F1) memanggil Connector FastAPI; Chart (F2) hanya merender respons.")

    # --- Slice F1: Initial Form (sidebar) ---
    with st.sidebar:
        st.header("Filter screener")
        default_end = date.today()
        default_start = default_end - timedelta(days=365)

        ticker_options: list[str] = list(FALLBACK_TICKERS)
        if _api_headers():
            try:
                ticker_options = fetch_ticker_symbols()
            except (requests.RequestException, KeyError, TypeError):
                st.caption("Tidak bisa memuat daftar ticker dari API — memakai contoh default.")
        else:
            st.caption("Atur **API_SECRET_KEY** di `.env` agar daftar ticker diambil dari database.")

        default_ix = 0
        if "BBCA.JK" in ticker_options:
            default_ix = ticker_options.index("BBCA.JK")
        ticker = st.selectbox(
            "Ticker",
            options=ticker_options,
            index=default_ix,
            help="Simbol dari `company_metadata` (sumber: API `/api/v1/tickers`).",
        )

        date_from = st.date_input("Dari tanggal", value=default_start)
        date_to = st.date_input("Sampai tanggal", value=default_end)

        st.subheader("Indikator")
        st.caption("Pilih kelompok sesuai PRD — data sudah dihitung di ETL (hanya dibaca).")
        c1, c2, c3 = st.columns(3)
        ma5 = c1.checkbox("MA 5", value=True)
        ma20 = c2.checkbox("MA 20", value=True)
        ma50 = c3.checkbox("MA 50", value=False)
        bollinger = st.checkbox(
            "Bollinger Bands (atas / tengah / bawah)",
            value=True,
            help="Menampilkan bb_upper, bb_middle, bb_lower.",
        )
        c4, c5 = st.columns(2)
        stoch_k = c4.checkbox("Stochastic %K", value=True)
        stoch_d = c5.checkbox("Stochastic %D", value=False)

        indicators = build_indicator_columns(
            ma5=ma5,
            ma20=ma20,
            ma50=ma50,
            bollinger=bollinger,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
        )

        run = st.button("Run Screener", type="primary")

    if not run:
        st.info('Atur filter di sidebar lalu klik **Run Screener**.')
        return

    if date_from > date_to:
        st.error("Tanggal awal tidak boleh lebih besar dari tanggal akhir.")
        return

    if not indicators:
        st.warning("Pilih minimal satu indikator.")
        return

    if not _api_headers():
        st.error(
            "Variabel **API_SECRET_KEY** tidak ada di `.env` (root project). "
            "Wajib diisi agar header X-API-Key dapat dikirim ke Connector."
        )
        return

    try:
        with st.spinner("Memanggil Connector API…"):
            screen_json = fetch_screen(ticker, date_from, date_to, indicators)
            ohlcv = fetch_historical_ohlcv(ticker, date_from, date_to)
    except requests.HTTPError as e:
        st.error(f"HTTP error dari API: {e.response.status_code} — {e.response.text[:500]}")
        return
    except requests.RequestException as e:
        st.error(f"Gagal menghubungi API ({API_BASE}): {e}")
        return

    rows = screen_json.get("data", [])
    pagination = screen_json.get("pagination", {})
    st.subheader(f"Hasil: **{screen_json.get('ticker', ticker)}**")
    st.write(
        f"Total baris (server): **{pagination.get('total_records', '?')}** "
        f"— halaman **{pagination.get('page', 1)}** / ukuran **{pagination.get('page_size', len(rows))}**"
    )

    if not rows:
        st.warning("Tidak ada data indikator untuk rentang ini. Pastikan ETL sudah dijalankan.")
        return

    df_chart = build_chart_df(rows, ohlcv)
    if df_chart.empty or not all(
        c in df_chart.columns for c in ["open_price", "high_price", "low_price", "close_price"]
    ):
        st.warning(
            "Tidak bisa menggambar candlestick: data OHLCV tidak tersedia atau tidak overlap dengan indikator. "
            "Jalankan ETL dan pastikan FastAPI dapat mengakses TimescaleDB."
        )
        df_fallback = pd.DataFrame(rows)
        st.dataframe(df_fallback, use_container_width=True)
        return

    # --- Slice F2: Calculation Chart (Plotly interaktif) ---
    fig = make_figure(df_chart, indicators)
    st.plotly_chart(fig, use_container_width=True)

    # Tabel validasi mentah
    st.subheader("Data mentah (validasi)")
    st.dataframe(df_chart, use_container_width=True, height=360)


if __name__ == "__main__":
    main()
