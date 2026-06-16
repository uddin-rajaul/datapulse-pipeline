{{
    config(
        materialized='table',
        schema='gold'
    )
}}

with intermediate as (
    select * from {{ ref('int_air_quality') }}
)

select
    city,
    date_trunc('day', observed_at)::date as observed_date,
    count(*) as reading_count,
    round(avg(pm2_5)::numeric, 2) as avg_pm25,
    round(max(pm2_5)::numeric, 2) as max_pm25,
    round(min(pm2_5)::numeric, 2) as min_pm25,
    round(avg(pm10)::numeric, 2) as avg_pm10,
    round(max(pm10)::numeric, 2) as max_pm10,
    round(avg(ow_aqi)::numeric, 1) as avg_aqi,
    max(ow_aqi) as max_aqi,
    count(*) filter (where ow_aqi >= 4) as unhealthy_reading_count
from intermediate
group by 1, 2
