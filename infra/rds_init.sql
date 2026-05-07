-- =============================================================================
-- datapulse-pipeline: RDS initialization script
-- Run once as datapulse_admin against the 'datapulse' database.
-- Safe to re-run: all statements use IF NOT EXISTS / DO NOTHING patterns.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Schemas
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;


-- -----------------------------------------------------------------------------
-- 2. Users
-- Run these only if users don't already exist.
-- Passwords are placeholders — replace before running.
-- In production, use AWS Secrets Manager or SSM Parameter Store.
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'datapulse_writer') THEN
        CREATE USER datapulse_writer WITH PASSWORD 'REPLACE_ME_WRITER';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'datapulse_reader') THEN
        CREATE USER datapulse_reader WITH PASSWORD 'REPLACE_ME_READER';
    END IF;
END
$$;


-- -----------------------------------------------------------------------------
-- 3. Privileges: datapulse_writer
-- Full access to bronze, silver, gold schemas.
-- Also needs USAGE + CREATE so it can create tables (dbt does this).
-- -----------------------------------------------------------------------------
GRANT USAGE, CREATE ON SCHEMA bronze TO datapulse_writer;
GRANT USAGE, CREATE ON SCHEMA silver TO datapulse_writer;
GRANT USAGE, CREATE ON SCHEMA gold   TO datapulse_writer;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bronze TO datapulse_writer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA silver TO datapulse_writer;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gold   TO datapulse_writer;

-- Make sure future tables created in these schemas also get the right perms.
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT ALL PRIVILEGES ON TABLES TO datapulse_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA silver GRANT ALL PRIVILEGES ON TABLES TO datapulse_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold   GRANT ALL PRIVILEGES ON TABLES TO datapulse_writer;

-- Sequences (needed for BIGSERIAL columns like id)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA bronze TO datapulse_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT USAGE, SELECT ON SEQUENCES TO datapulse_writer;


-- -----------------------------------------------------------------------------
-- 4. Privileges: datapulse_reader
-- SELECT only on gold schema. Streamlit uses this user.
-- No access to bronze or silver — raw/intermediate data is not exposed.
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA gold TO datapulse_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO datapulse_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO datapulse_reader;


-- -----------------------------------------------------------------------------
-- 5. Bronze table
-- This is the raw landing zone. Every column maps directly to the
-- OpenWeather API response — no transformations happen here.
--
-- Design decisions:
--   - BIGSERIAL id: stable surrogate key, avoids composite PK in app queries
--   - TIMESTAMPTZ: always store with timezone — RDS default is UTC, keep it
--   - UNIQUE (city, observed_at): idempotency guard at DB level.
--     If Airflow re-runs the same hour, ON CONFLICT DO NOTHING is safe.
--   - NUMERIC(8,2) for pollutants: OpenWeather returns 2 decimal places.
--     Using FLOAT would introduce floating-point noise into analytics.
--   - ow_aqi is SMALLINT: it's only ever 1–5
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.air_quality_raw (
    id              BIGSERIAL       PRIMARY KEY,
    city            VARCHAR(50)     NOT NULL,
    lat             NUMERIC(8, 4)   NOT NULL,
    lon             NUMERIC(8, 4)   NOT NULL,
    observed_at     TIMESTAMPTZ     NOT NULL,
    ingested_at     TIMESTAMPTZ     NOT NULL DEFAULT now(),
    ow_aqi          SMALLINT,
    pm2_5           NUMERIC(8, 2),
    pm10            NUMERIC(8, 2),
    co              NUMERIC(8, 2),
    no              NUMERIC(8, 2),
    no2             NUMERIC(8, 2),
    o3              NUMERIC(8, 2),
    so2             NUMERIC(8, 2),
    nh3             NUMERIC(8, 2),
    UNIQUE (city, observed_at)
);

-- Index on city + observed_at for time-range queries (dbt incremental models
-- will filter on observed_at heavily).
CREATE INDEX IF NOT EXISTS idx_aqr_city_observed
    ON bronze.air_quality_raw (city, observed_at DESC);


-- -----------------------------------------------------------------------------
-- 6. Verify
-- Run this manually after executing the script to confirm setup.
-- \dn+            -- list schemas
-- \dp bronze.*    -- show table privileges
-- SELECT * FROM bronze.air_quality_raw LIMIT 0;
-- -----------------------------------------------------------------------------
