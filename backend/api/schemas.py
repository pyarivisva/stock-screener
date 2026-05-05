from datetime import date, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_records: int
    total_pages: int


class TickerMetadata(BaseModel):
    ticker_id: UUID
    symbol: str
    company_name: str
    sector: str | None = None
    exchange: str | None = None
    source: str | None = None
    created_at: datetime


class StockPrice(BaseModel):
    symbol: str
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    source: str | None = None
    ingested_at: datetime


class TechnicalIndicators(BaseModel):
    symbol: str
    trade_date: date
    close_price: float
    ma5: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    computed_at: datetime


class HistoricalStockResponse(BaseModel):
    pagination: PaginationMeta
    data: list[StockPrice]


class IndicatorsResponse(BaseModel):
    pagination: PaginationMeta
    data: list[TechnicalIndicators]


class LatestIndicatorResponse(BaseModel):
    data: TechnicalIndicators | None = None


class TickersResponse(BaseModel):
    pagination: PaginationMeta
    data: list[TickerMetadata]


class ScreenerRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)
    date_from: date | None = None
    date_to: date | None = None
    min_stoch_k: float | None = Field(default=None, ge=0, le=100)


class ScreenRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=32)
    date_from: date | None = None
    date_to: date | None = None
    indicators: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_date_window(self) -> "ScreenRequest":
        """PRD §12.2 — rentang tanggal maksimal 5 tahun."""
        df, dt = self.date_from, self.date_to
        if df is not None and dt is not None:
            if dt < df:
                raise ValueError("date_to harus lebih besar atau sama dengan date_from.")
            max_span = timedelta(days=365 * 5 + 5)
            if (dt - df) > max_span:
                raise ValueError("Rentang tanggal maksimal 5 tahun per permintaan.")
        return self


class ScreenRow(BaseModel):
    trade_date: date
    close_price: float
    ma5: float | None = None
    ma20: float | None = None
    ma50: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None


class ScreenResponse(BaseModel):
    ticker: str
    pagination: PaginationMeta
    data: list[ScreenRow]


class ScreenerResult(BaseModel):
    symbol: str
    trade_date: date
    close_price: float
    ma5: float | None = None
    ma20: float | None = None
    stoch_k: float | None = None


class ScreenerResponse(BaseModel):
    pagination: PaginationMeta
    data: list[ScreenerResult]
