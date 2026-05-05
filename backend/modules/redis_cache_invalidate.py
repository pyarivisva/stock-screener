"""
Invalidasi kunci cache Connector setelah ETL load (PRD §9.3).

Memakai Redis DB yang sama dengan cache API (REDIS_CACHE_URL / DB 0).
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse, urlunparse

import redis.asyncio as redis_async

logger = logging.getLogger(__name__)


def _resolve_cache_url() -> str | None:
    raw = (os.getenv("REDIS_CACHE_URL") or "").strip()
    if raw:
        return raw
    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = os.getenv("REDIS_PORT", "6379")
    password = (os.getenv("REDIS_PASSWORD") or "").strip()
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/0"


async def invalidate_connector_caches_for_symbol(redis_url: str | None, symbol: str) -> None:
    """
    Hapus pola screen:{SYMBOL}:*, indicators:{SYMBOL}:*, dan kunci latest:{SYMBOL}.
    """
    url = (redis_url or "").strip() or _resolve_cache_url()
    if not url:
        return

    sym = symbol.upper()
    client = redis_async.from_url(url, decode_responses=True)
    try:
        deleted = 0
        async for key in client.scan_iter(match=f"screen:{sym}:*", count=200):
            await client.delete(key)
            deleted += 1
        async for key in client.scan_iter(match=f"indicators:{sym}:*", count=200):
            await client.delete(key)
            deleted += 1
        if await client.delete(f"latest:{sym}"):
            deleted += 1
        if deleted:
            logger.info("Redis invalidate untuk %s: %s kunci dihapus.", sym, deleted)
    except Exception as exc:
        logger.warning("Gagal invalidate Redis untuk %s: %s", sym, exc)
    finally:
        await client.close()


async def invalidate_ticker_list_pages(redis_url: str | None) -> None:
    """Hapus semua kunci tickers:all:page:* (setelah metadata berubah)."""
    url = (redis_url or "").strip() or _resolve_cache_url()
    if not url:
        return
    client = redis_async.from_url(url, decode_responses=True)
    try:
        n = 0
        async for key in client.scan_iter(match="tickers:all:page:*", count=200):
            await client.delete(key)
            n += 1
        if n:
            logger.info("Redis invalidate daftar ticker: %s kunci dihapus.", n)
    except Exception as exc:
        logger.warning("Gagal invalidate daftar ticker Redis: %s", exc)
    finally:
        await client.close()


def redis_cache_url_for_etl() -> str | None:
    """URL cache untuk worker ETL; paksa /0 jika URL tanpa path DB."""
    u = _resolve_cache_url()
    if not u:
        return None
    parsed = urlparse(u)
    if not parsed.path or parsed.path == "/":
        return urlunparse(parsed._replace(path="/0"))
    return u
