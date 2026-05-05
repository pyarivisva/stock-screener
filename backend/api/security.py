"""
Autentikasi API Key — PRD §12.1 (header `X-API-Key`).
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from backend.api.config import get_settings


def _constant_time_equals(provided: str, expected: str) -> bool:
    """Perbandingan aman timing; panjang berbeda → tidak cocok tanpa memanggil compare_digest panjang beda."""
    pa = provided.encode("utf-8")
    pb = expected.encode("utf-8")
    if len(pa) != len(pb):
        return False
    return secrets.compare_digest(pa, pb)


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """
    Memvalidasi header X-API-Key terhadap API_SECRET_KEY di environment.
    """
    settings = get_settings()
    secret = (settings.api_secret_key or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_SECRET_KEY belum dikonfigurasi di server.",
        )
    if not x_api_key or not _constant_time_equals(x_api_key, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key tidak valid atau header X-API-Key tidak ada.",
        )
    return x_api_key
