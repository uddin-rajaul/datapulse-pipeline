{{
    config(
        materialized='table',
        schema='gold'
    )
}}
/*
Materialized as table, not incremental:
  Full-history recomputation at city-level daily aggregation over ~35K rows
  is negligible. Incremental would add complexity (merge key, lookback window)
  without measurable benefit at this scale. Revisit if data volume grows 100x.
*/

with intermediate as (
    select * from {{ ref('int_air_quality') }}
),

daily as (
    select
        city,
        date_trunc('day', observed_at)::date as observed_date,
        count(*) as reading_count,
        round(avg(pm2_5)::numeric, 2) as avg_pm25,
        round(max(pm2_5)::numeric, 2) as max_pm25,
        {{ var('who_daily_pm25_threshold') }} as who_daily_threshold_ug_m3,
        {{ var('who_annual_pm25_threshold') }} as who_annual_threshold_ug_m3
    from intermediate
    group by 1, 2
)

select
    *,
    avg_pm25 > who_daily_threshold_ug_m3 as exceeds_daily_who,
    round(avg(avg_pm25) over (
        partition by city
        order by observed_date
        rows between 6 preceding and current row
    )::numeric, 2) as rolling_7day_avg_pm25
from daily
