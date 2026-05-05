"""
Task Celery untuk pipeline ETL (PRD §6).

Task `run_daily_etl` memanggil coroutine utama `main_etl.main()` dengan `asyncio.run`.
Task `flush_ticker_list_cache` menjadwalkan flush kunci `tickers:all:*` (PRD §6.2 invalidate_cache).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from backend.tasks.celery_app import app

logger = logging.getLogger(__name__)


def _ensure_backend_on_path() -> Path:
    """
    `main_etl.py` mengimpor `modules.*` relatif terhadap folder `backend/`.
    Pastikan `backend/` ada di sys.path saat task dijalankan dari project root.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    backend_str = str(backend_dir)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)
    return backend_dir


@app.task(
    bind=True,
    name="backend.tasks.etl_tasks.run_daily_etl",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
    retry_jitter=True,
)
def run_daily_etl(self) -> str:
    """
    Menjalankan ETL harian (Extract → Transform → Load) seperti `main_etl.py`.

    Dipanggil oleh Beat setiap hari pukul 17:00 (lihat `celery_app.py`).
    Retry otomatis hingga 3 kali dengan backoff eksponensial (PRD §6.3).
    """
    logger.info("Celery task run_daily_etl dimulai (task_id=%s)", self.request.id)
    backend_dir = _ensure_backend_on_path()

    from dotenv import load_dotenv

    load_dotenv(backend_dir.parent / ".env")

    # Import setelah path siap (modules di bawah backend/)
    from main_etl import main as etl_main

    asyncio.run(etl_main())

    logger.info("Celery task run_daily_etl selesai")
    return "ok"


@app.task(name="backend.tasks.etl_tasks.flush_ticker_list_cache")
def flush_ticker_list_cache() -> str:
    """
    Hapus cache Redis untuk daftar ticker (PRD §9.3 `tickers:all:*`).
    Dijadwalkan Beat 18:10 sebagai pelengkap invalidasi pasca-ETL.
    """
    backend_dir = _ensure_backend_on_path()
    from dotenv import load_dotenv

    load_dotenv(backend_dir.parent / ".env")

    from modules.redis_cache_invalidate import (
        invalidate_ticker_list_pages,
        redis_cache_url_for_etl,
    )

    asyncio.run(invalidate_ticker_list_pages(redis_cache_url_for_etl()))
    logger.info("flush_ticker_list_cache selesai")
    return "ok"
