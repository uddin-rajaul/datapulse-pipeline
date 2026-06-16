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
    aqi_label,
    count(*) as reading_count
from intermediate
group by 1, 2, 3
order by 1, 2, 3
