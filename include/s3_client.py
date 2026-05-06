import json
import logging
import boto3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_s3_key(city: str, observed_at: str) -> str:
    """
    Build a deterministic S3 key from city and observation time.
    Same city + same hour always produces the same key.
    This is what makes our DAG idempotent — writing twice
    to the same key just overwrites with identical data.

    Output format:
    city=kathmandu/year=2026/month=04/day=19/hour=15.json
    """
    dt = datetime.fromisoformat(observed_at)
    return (
        f"city={city}/"
        f"year={dt.year}/"
        f"month={dt.month:02d}/"
        f"day={dt.day:02d}/"
        f"hour={dt.hour:02d}.json"
    )


def write_to_s3(record: dict, bucket: str) -> str:
    """
    Write a single air quality record to S3 as JSON.
    Uses the deterministic key so re-runs are safe.
    Returns the S3 key it wrote to.
    """
    key = get_s3_key(record["city"], record["observed_at"])

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(record, indent=2),
        ContentType="application/json",
    )

    logger.info(f"Written to s3://{bucket}/{key}")
    return key


def write_all_to_s3(records: list[dict], bucket: str) -> list[str]:
    """
    Write all city records to S3.
    Logs errors per record but continues — same pattern
    as fetch_all_cities. One city failing should not
    block the others from being saved.
    Returns list of keys successfully written.
    """
    written_keys = []
    for record in records:
        try:
            key = write_to_s3(record, bucket)
            written_keys.append(key)
        except Exception as e:
            logger.error(
                f"Failed to write {record.get('city')} to S3: {e}"
            )
    return written_keys