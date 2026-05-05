# Stock Screener

Aplikasi **stock screener** berbasis arsitektur **Data Source → ETL → TimescaleDB → Redis → FastAPI → Streamlit** (lihat [`prd.md`](prd.md) untuk detail lengkap). Data indikator teknikal (MA, Bollinger, Stochastic) dihitung di **ETL** dan disajikan lewat **API Connector** tanpa komputasi ulang di layer baca.

## Isi repositori (ringkas)

| Bagian | Peran |
|--------|--------|
| [`database/init.sql`](database/init.sql) | Skema TimescaleDB (hypertable, indeks) |
| [`backend/modules/`](backend/modules/) | ETL slicing: fetcher, kalkulator, writer (`asyncpg`) |
| [`backend/main_etl.py`](backend/main_etl.py) | Skrip ETL orkestrasi (contoh ticker) |
| [`backend/api/`](backend/api/) | FastAPI: config, pool DB/Redis, routes, rate limit, API key |
| [`backend/tasks/`](backend/tasks/) | Celery app + task harian |
| [`frontend/app.py`](frontend/app.py) | UI Streamlit (form + chart Plotly) |
| [`docker-compose.yml`](docker-compose.yml) | Stack: TimescaleDB, Redis, pgAdmin, API, worker, beat, frontend |
| [`Dockerfile`](Dockerfile) | Image Python tunggal untuk layanan aplikasi |

## Prasyarat

- **Docker Desktop** (atau Docker Engine + Compose v2) untuk menjalankan stack lengkap  
- **Python 3.10+** jika menjalankan API / ETL / Streamlit di luar container  
- Di Windows: hindari bentrok **PostgreSQL lokal** dengan port DB Docker — proyek ini memetakan TimescaleDB ke host **`5433`** secara default (lihat `POSTGRES_PORT` di `.env`)

## Persiapan environment

1. Salin contoh environment:

   ```bash
   copy .env.example .env
   ```

   (Linux/macOS: `cp .env.example .env`)

2. Isi `.env` minimal:

   - **`POSTGRES_*`**, **`PGADMIN_*`**
   - **`API_SECRET_KEY`** — wajib untuk endpoint API yang dilindungi (header `X-API-Key` harus sama)
   - **`REDIS_CELERY_BROKER_URL`** / **`REDIS_CELERY_RESULT_BACKEND`** jika menjalankan Celery (default ada di `.env.example`)

3. **Jangan** commit `.env` (sudah diabaikan di [`.gitignore`](.gitignore)).

## Menjalankan stack lengkap (Docker)

Dari root proyek (folder yang berisi `docker-compose.yml`):

```bash
docker compose up -d --build
```

Layanan yang berjalan:

| Layanan | Akses | Keterangan |
|---------|--------|------------|
| **API** (FastAPI) | http://localhost:8000 | Docs: http://localhost:8000/docs |
| **Frontend** (Streamlit) | http://localhost:8501 | Memanggil API; set `API_BASE_URL` jika perlu |
| **pgAdmin** | http://localhost:5050 | GUI ke TimescaleDB |
| **TimescaleDB** | `localhost` port **5433** → container `5432` | Kredensial dari `.env` |
| **Redis** | `localhost:6379` | Cache API (DB 0), broker Celery (DB 1), result (DB 2) |
| **Celery worker / beat** | — | ETL terjadwal; lihat [`backend/tasks/celery_app.py`](backend/tasks/celery_app.py) |

Hentikan stack:

```bash
docker compose down
```

Data DB tetap ada di volume sampai `docker compose down -v`.

## Menjalankan tanpa Docker (development lokal)

Asumsi: **TimescaleDB + Redis** sudah jalan (misalnya lewat `docker compose up -d` hanya untuk `timescaledb`, `redis`, dan opsional `pgadmin`).

1. Buat virtual environment dan install dependensi:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **ETL** (isi database):

   ```bash
   python backend/main_etl.py
   ```

3. **API**:

   ```bash
   uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Streamlit** (terminal lain, dengan venv sama):

   ```bash
   streamlit run frontend/app.py
   ```

5. **Celery** (opsional, dua terminal):

   ```bash
   celery -A backend.tasks.celery_app worker --pool=solo --loglevel=info
   celery -A backend.tasks.celery_app beat --loglevel=info
   ```

Pastikan variabel di `.env` mengarah ke host yang benar (`127.0.0.1`, port DB **5433** jika memakai compose default).

## Autentikasi API (Phase 8)

Endpoint di bawah `/api/v1/...` (kecuali **`GET /health`**) memerlukan header:

```http
X-API-Key: <nilai sama dengan API_SECRET_KEY di .env>
```

Contoh dengan `curl` (sesuaikan URL dan key):

```bash
curl -s -H "X-API-Key: YOUR_SECRET" "http://127.0.0.1:8000/api/v1/tickers"
```

Streamlit memuat `API_SECRET_KEY` dari `.env` dan mengirim header tersebut secara otomatis.

## Alur data singkat

1. **ETL** mengambil OHLCV (mis. yfinance), menghitung indikator dengan **Pandas**, lalu **upsert** ke `stock_prices` dan `stock_indicators`.
2. **FastAPI** hanya **SELECT** + cache Redis (read-through) untuk pola baca yang berat.
3. **Streamlit** memanggil **`POST /api/v1/screen`** dan **`GET .../stocks/.../historical`** untuk candlestick + overlay.

## Dokumentasi produk

Spesifikasi lengkap: [`prd.md`](prd.md).
