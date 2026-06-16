-- observed_at should never be in the future.
-- A future timestamp means the API returned an invalid datetime
-- or the ingestion pipeline has a clock skew issue.
select
    city,
    observed_at,
    ingested_at
from {{ ref('int_air_quality') }}
where observed_at > current_timestamp
