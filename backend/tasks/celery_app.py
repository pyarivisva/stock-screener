"""
Aplikasi Celery — broker & result backend Redis (PRD §10.1).

Cara menjalankan (dari root project `stock-screener`, dengan venv aktif):

1) Worker (proses task):
   celery -A backend.tasks.celery_app worker --loglevel=info

2) Beat (penjadwal; kirim task sesuai crontab):
   celery -A backend.tasks.celery_app beat --loglevel=info

Pastikan Redis sudah berjalan (mis. `docker compose up -d`) dan variabel
REDIS_CELERY_BROKER_URL / REDIS_CELERY_RESULT_BACKEND sesuai .env.
"""

from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Muat .env dari root project sebelum membaca URL Redis
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

# PRD: broker DB 1, result backend DB 2 (pisah dari cache DB 0)
REDIS_CELERY_BROKER_URL = os.getenv(
    "REDIS_CELERY_BROKER_URL",
    "redis://127.0.0.1:6379/1",
)
REDIS_CELERY_RESULT_BACKEND = os.getenv(
    "REDIS_CELERY_RESULT_BACKEND",
    "redis://127.0.0.1:6379/2",
)

# Instance Celery yang diakses oleh `celery -A backend.tasks.celery_app ...`
app = Celery(
    "stock_screener",
    broker=REDIS_CELERY_BROKER_URL,
    backend=REDIS_CELERY_RESULT_BACKEND,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=os.getenv("CELERY_TIMEZONE", "Asia/Jakarta"),
    enable_utc=False,
    task_track_started=True,
    task_time_limit=60 * 60,
    worker_prefetch_multiplier=1,
)

# PRD §6.2: ETL harian ~tutup bursa; invalidate daftar ticker terjadwal 18:10
app.conf.beat_schedule = {
    "run-daily-etl-17": {
        "task": "backend.tasks.etl_tasks.run_daily_etl",
        "schedule": crontab(hour=17, minute=0),
    },
    "flush-ticker-list-cache-1810": {
        "task": "backend.tasks.etl_tasks.flush_ticker_list_cache",
        "schedule": crontab(hour=18, minute=10),
    },
}

# Daftarkan modul task (Celery memuat `include` saat worker/beat start)
from backend.tasks import etl_tasks  # noqa: E402, F401
