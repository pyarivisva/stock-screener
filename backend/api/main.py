import logging

from fastapi import FastAPI

from backend.api.config import get_settings
from backend.api.cache.redis_client import close_redis_pool, init_redis_pool
from backend.api.database import close_database_pool, init_database_pool
from backend.api.routes.indicators import router as indicators_router
from backend.api.routes.screen import router as screen_router
from backend.api.routes.screener import router as screener_router
from backend.api.routes.stocks import router as stocks_router
from backend.api.routes.tickers import router as tickers_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API Connector untuk Stock Screener berbasis TimescaleDB + Redis.",
)


@app.on_event("startup")
async def on_startup() -> None:
    """
    Inisialisasi resource aplikasi saat server dinyalakan.
    """
    app.state.db_pool = await init_database_pool()
    app.state.redis_client = await init_redis_pool()
    logger.info("API startup selesai. DB pool dan Redis siap.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """
    Menutup resource aplikasi saat server dimatikan.
    """
    await close_database_pool(getattr(app.state, "db_pool", None))
    await close_redis_pool(getattr(app.state, "redis_client", None))
    logger.info("API shutdown selesai. Resource ditutup.")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(stocks_router, prefix="/api/v1")
app.include_router(indicators_router, prefix="/api/v1")
app.include_router(screener_router, prefix="/api/v1")
app.include_router(screen_router, prefix="/api/v1")
app.include_router(tickers_router, prefix="/api/v1")
