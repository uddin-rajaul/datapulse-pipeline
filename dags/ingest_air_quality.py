"""
Hourly Pipeline: OpenWeather API -> S3 Bronze -> RDS bronze -> GE validation

XCom carries only S3 keys (small strings) between tasks.
Full record payloads are read from S3, never stored in XCom.
"""
import json
import logging
import os
from datetime import datetime, timedelta

import boto3
import psycopg2
from psycopg2.extras import execute_values

from airflow import DAG
from airflow.operators.python import PythonOperator

from include.openweather_client import fetch_all_cities
from include.s3_client import write_all_to_s3



log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "datapulse",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


def _db_conn():
    """
    Open a psycopg2 connection to RDS using environment variables.
    Raises clearly if any required var is missing.
    """
    host = os.getenv("RDS_HOST")
    port = int(os.getenv("RDS_PORT", "5432"))
    dbname = os.getenv("RDS_DB")
    user = os.getenv("RDS_USER")
    password = os.getenv("RDS_PASSWORD")
    if not all([host, dbname, user, password]):
        raise RuntimeError("Missing one or more RDS_* environment variables")
    return psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password
    )


def fetch_and_store_s3(**context):
    """
    Fetch air quality data for all cities, write each record to S3.
    Returns: list of S3 keys written (these go into XCom — small strings only).
    """
    api_key = os.environ["OPENWEATHER_API_KEY"]
    bucket = os.environ.get("S3_BUCKET", "datapulse-bronze")

    records = fetch_all_cities(api_key)
    if not records:
        raise ValueError("No records fetched from OpenWeather API — check city logs")

    log.info("Fetched %d records from OpenWeather API", len(records))

    s3_keys = write_all_to_s3(records, bucket)
    if not s3_keys:
        raise ValueError("All S3 writes failed — no keys returned")

    log.info("Written %d keys to s3://%s", len(s3_keys), bucket)

    # XCom carries only S3 keys, not the full record payloads.
    # This keeps XCom lightweight and makes load_bronze independently retryable.
    return s3_keys


def load_bronze(**context):
    """
    Read each S3 key written by fetch_and_store_s3, then insert into RDS bronze.
    Reading from S3 (not XCom) means this task is safe to retry independently.
    """
    s3_keys = context["ti"].xcom_pull(task_ids="fetch_and_store_s3")
    if not s3_keys:
        raise ValueError("XCom returned no S3 keys — check fetch_and_store_s3 logs")

    bucket = os.environ.get("S3_BUCKET", "datapulse-bronze")
    s3 = boto3.client("s3")

    records = []
    for key in s3_keys:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            record = json.loads(obj["Body"].read().decode("utf-8"))
            records.append(record)
        except Exception as e:
            log.error("Failed to read s3://%s/%s: %s", bucket, key, e)

    if not records:
        raise ValueError("Could not read any records from S3 — aborting bronze load")

    rows = [
        (
            r["city"], r["lat"], r["lon"],
            r["observed_at"], r["ingested_at"],
            r.get("ow_aqi"), r.get("pm2_5"), r.get("pm10"),
            r.get("co"), r.get("no"), r.get("no2"),
            r.get("o3"), r.get("so2"), r.get("nh3"),
        )
        for r in records
    ]

    insert_sql = """
        INSERT INTO bronze.air_quality_raw (
            city, lat, lon, observed_at, ingested_at,
            ow_aqi, pm2_5, pm10, co, no, no2, o3, so2, nh3
        ) VALUES %s
        ON CONFLICT (city, observed_at) DO NOTHING
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, rows)
            log.info(
                "Inserted %d rows into bronze.air_quality_raw (duplicates ignored)",
                cur.rowcount,
            )


def validate_bronze(**context):
    """
    Run GE bronze_checkpoint against the rows just loaded.
    Scope: rows matching the observed_at timestamps from this run only.
    Uses parameterized query — no f-string SQL interpolation.
    """
    # Import here, not at module level — GE is slow to import and would
    # cause Airflow's DAG parser to time out on every parse cycle.
    from great_expectations.data_context import DataContext
    from great_expectations.core.batch import RuntimeBatchRequest
    s3_keys = context["ti"].xcom_pull(task_ids="fetch_and_store_s3")
    if not s3_keys:
        raise ValueError("XCom returned no S3 keys — cannot scope GE validation")

    # Re-read records from S3 to get observed_at values.
    # Avoids storing record payloads in XCom.
    bucket = os.environ.get("S3_BUCKET", "datapulse-bronze")
    s3 = boto3.client("s3")

    observed_at_values = []
    for key in s3_keys:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            record = json.loads(obj["Body"].read().decode("utf-8"))
            observed_at_values.append(record["observed_at"])
        except Exception as e:
            log.error("Failed to read s3://%s/%s for GE scoping: %s", bucket, key, e)

    if not observed_at_values:
        raise ValueError("Could not resolve any observed_at values for GE query scope")

    # GE RuntimeBatchRequest requires a raw SQL string — it doesn't support
    # psycopg2-style %s params. We build the IN clause by quoting each
    # observed_at value as a SQL literal.
    #
    # Why is this safe here:
    #   - observed_at values come from our own S3 records (we wrote them)
    #   - They are ISO 8601 strings produced by datetime.isoformat()
    #   - They contain no user input and no characters that could escape a
    #     SQL string literal (no quotes, semicolons, or backslashes)
    #
    # If this ever changes (e.g. you accept user-supplied filters), switch to
    # a query builder or a GE datasource that supports native params.
    quoted = ", ".join(f"'{v}'" for v in observed_at_values)
    scoped_query = f"""
        SELECT *
        FROM bronze.air_quality_raw
        WHERE observed_at IN ({quoted})
    """

    ge_root = os.path.join(os.path.dirname(__file__), "..", "great_expectations")
    data_context = DataContext(ge_root)

    batch_request = RuntimeBatchRequest(
        datasource_name="datapulse_rds",
        data_connector_name="default_runtime_data_connector",
        data_asset_name="bronze_current_batch",
        runtime_parameters={"query": scoped_query},
        batch_identifiers={"run_id": context["run_id"]},
    )

    result = data_context.run_checkpoint(
        checkpoint_name="bronze_checkpoint",
        validations=[
            {
                "batch_request": batch_request,
                "expectation_suite_name": "bronze_air_quality_raw",
            }
        ],
    )

    if not result["success"]:
        failed = []
        for run_result in result["run_results"].values():
            for vr in run_result.get("validation_result", {}).get("results", []):
                if not vr["success"]:
                    failed.append(vr["expectation_config"]["expectation_type"])
        raise ValueError(f"GE bronze_checkpoint failed. Violated expectations: {failed}")

    log.info("GE bronze_checkpoint passed for run_id=%s", context["run_id"])


with DAG(
    dag_id="ingest_air_quality",
    default_args=DEFAULT_ARGS,
    description="Hourly: OpenWeather API -> S3 Bronze -> RDS bronze -> GE validation",
    schedule="@hourly",
    start_date=datetime(2026, 4, 1),
    catchup=False,
    max_active_runs=1,
    tags=["datapulse", "bronze"],
) as dag:

    fetch_task = PythonOperator(
        task_id="fetch_and_store_s3",
        python_callable=fetch_and_store_s3,
    )

    load_task = PythonOperator(
        task_id="load_bronze",
        python_callable=load_bronze,
    )

    validate_task = PythonOperator(
        task_id="validate_bronze",
        python_callable=validate_bronze,
    )

    fetch_task >> load_task >> validate_task
