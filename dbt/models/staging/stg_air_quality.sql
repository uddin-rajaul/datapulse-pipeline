with source as (
    select * from {{ source('raw', 'air_quality_raw') }}
),

deduped as (
    select
        city::varchar(50) as city,
        lat::numeric(8, 4) as lat,
        lon::numeric(8, 4) as lon,
        observed_at::timestamptz as observed_at,
        ingested_at::timestamptz as ingested_at,
        ow_aqi::smallint as ow_aqi,
        pm2_5::numeric(8, 2) as pm2_5,
        pm10::numeric(8, 2) as pm10,
        co::numeric(8, 2) as co,
        no::numeric(8, 2) as no,
        no2::numeric(8, 2) as no2,
        o3::numeric(8, 2) as o3,
        so2::numeric(8, 2) as so2,
        nh3::numeric(8, 2) as nh3,
        row_number() over (
            partition by city, observed_at
            order by ingested_at desc
        ) as rn
    from source
)

select
    city,
    lat,
    lon,
    observed_at,
    ingested_at,
    ow_aqi,
    pm2_5,
    pm10,
    co,
    no,
    no2,
    o3,
    so2,
    nh3
from deduped
where rn = 1
