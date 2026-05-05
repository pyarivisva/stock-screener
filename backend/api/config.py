from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Konfigurasi APP
    app_name: str = "Stock Screener API"
    app_version: str = "0.1.0"
    app_env: str = "development"

    # Konfigurasi PostgreSQL (TimescaleDB)
    postgres_user: str = "stock_user"
    postgres_password: str = "postgres"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433
    postgres_db: str = "stock_screener"
    database_url: str | None = None

    # Konfigurasi Redis cache
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_ttl_historical: int = 300
    redis_ttl_indicators: int = 300
    # Override penuh URL Redis cache (harus memakai DB 0); jika kosong, dibangun dari host/port/password
    redis_cache_url: str | None = None

    # Pagination default
    default_page_size: int = 100
    max_page_size: int = 500

    # Keamanan API (PRD §12.1) — wajib diisi untuk endpoint yang dilindungi
    api_secret_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = ""
        if self.redis_password:
            auth = f":{self.redis_password}@"
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
