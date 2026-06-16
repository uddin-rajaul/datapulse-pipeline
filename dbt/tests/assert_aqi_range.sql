-- AQI must be between 1 and 5 per the OpenWeather scale.
-- Values outside this range indicate a parsing bug or API change.
select
    city,
    observed_at,
    ow_aqi
from {{ ref('int_air_quality') }}
where ow_aqi < 1 or ow_aqi > 5
