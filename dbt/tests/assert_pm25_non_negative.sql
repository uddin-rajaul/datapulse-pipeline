-- PM2.5 concentration cannot be negative.
-- Negative values indicate a sensor error or data corruption.
select
    city,
    observed_at,
    pm2_5
from {{ ref('int_air_quality') }}
where pm2_5 < 0
