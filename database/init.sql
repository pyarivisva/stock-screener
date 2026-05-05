-- 1. Aktifkan Extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2. Tabel Metadata Perusahaan
CREATE TABLE IF NOT EXISTS company_metadata (
    ticker_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    exchange VARCHAR(50),
    source VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Tabel Harga Saham (OHLCV) - Hypertable
CREATE TABLE IF NOT EXISTS stock_prices (
    ticker_id UUID NOT NULL REFERENCES company_metadata(ticker_id),
    trade_date DATE NOT NULL,
    open_price NUMERIC(18,4) NOT NULL,
    high_price NUMERIC(18,4) NOT NULL,
    low_price NUMERIC(18,4) NOT NULL,
    close_price NUMERIC(18,4) NOT NULL,
    volume BIGINT NOT NULL,
    source VARCHAR(50),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker_id, trade_date) -- Syarat utama TimescaleDB Hypertable
);

-- 4. Tabel Indikator Teknikal (Pre-computed) - Hypertable
CREATE TABLE IF NOT EXISTS stock_indicators (
    ticker_id UUID NOT NULL REFERENCES company_metadata(ticker_id),
    trade_date DATE NOT NULL,
    close_price NUMERIC(18,4) NOT NULL,
    ma5 NUMERIC(18,4),
    ma20 NUMERIC(18,4),
    ma50 NUMERIC(18,4),
    bb_upper NUMERIC(18,4),
    bb_middle NUMERIC(18,4),
    bb_lower NUMERIC(18,4),
    bb_width NUMERIC(18,4),
    stoch_k NUMERIC(8,4),
    stoch_d NUMERIC(8,4),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker_id, trade_date) -- Syarat utama TimescaleDB Hypertable
);

-- 5. Konversi ke Hypertable
SELECT create_hypertable('stock_prices', 'trade_date', if_not_exists => TRUE);
SELECT create_hypertable('stock_indicators', 'trade_date', if_not_exists => TRUE);

-- 6. Indexing untuk Read Performance (Connector Layer)
CREATE INDEX IF NOT EXISTS ix_company_metadata_sector ON company_metadata (sector);
CREATE INDEX IF NOT EXISTS ix_company_metadata_exchange ON company_metadata (exchange);
CREATE INDEX IF NOT EXISTS ix_stock_indicators_trade_date ON stock_indicators (trade_date DESC);
CREATE INDEX IF NOT EXISTS ix_stock_indicators_ma5_not_null ON stock_indicators (ma5) WHERE ma5 IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_stock_indicators_ma20_not_null ON stock_indicators (ma20) WHERE ma20 IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_stock_indicators_stoch_k_overbought ON stock_indicators (stoch_k) WHERE stoch_k > 80;