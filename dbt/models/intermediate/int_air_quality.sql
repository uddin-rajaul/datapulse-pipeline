{{
    config(
        materialized='incremental',
        unique_key=['city', 'observed_at'],
        on_schema_change='append_new_columns',
        incremental_strategy='merge'
    )
}}

with staging as (
    select * from {{ ref('stg_air_quality') }}
),

cleaned as (
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
        nh3,
        {{ get_aqi_label('ow_aqi') }} as aqi_label,
        {{ get_nepal_season('observed_at') }} as season
    from staging
    where pm2_5 is not null
      and ow_aqi between 1 and 5
)

select * from cleaned

{% if is_incremental() %}
where observed_at > (select max(observed_at) from {{ this }})
{% endif %}
