"""
Hourly Pipeline: Openweather API -> S3 Bronze + RDS bronze + validation

"""
import logging
import os
from datetime import datetime, timedelta

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from airflow import DAG
from airflow.operators.python import PythonOperator

from include.openweather_client import CITIES, fetch_all_cities
from include.s3_client import write_all_to_s3

from great_expectations.data_context import DataContext

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "datapulse",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


def _db_conn():
    """
    Open a psycopg2 connection to the RDS database using environment variables.
    """
    host = os.getenv("RDS_HOST")
    port = int(os.getenv("RDS_PORT", "5432"))
    dbname = os.getenv("RDS_DB")
    user = os.getenv("RDS_USER")
    password = os.getenv("RDS_PASSWORD")
    if not all([host, dbname, user, password]):
        raise RuntimeError("Missing one or more RDS_* environment variables")
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )


def fetch_and_store_s3(**context):
    """
    Fetch air quality data for all cities and store in S3 as json
    """
    api_key = os.environ["OPENWEATHER_API_KEY"]
    bucket = os.environ.get("S3_BUCKET", "datapulse-bronze")

    records = fetch_all_cities(api_key)

    if not records:
        raise ValueError("No records fetched from OpenWeather API - check logs for details")

    log.info("Fetched %s records from OpenWeather API", len(records))

    write_all_to_s3(records, bucket)
    log.info("Written %s records to S3 bucket %s", len(records), bucket)

    return records


def load_bronze(**context):
    """
    Load the fetched records from S3 into the RDS bronze table.
    """
    records = context["ti"].xcom_pull(task_ids="fetch_and_store_s3")

    if not records:
        raise ValueError("XCom pull returned no records - check previous task logs for details")

    rows = [
        (
            r["city"],
            r["lat"],
            r["lon"],
            r["observed_at"],
            r["ingested_at"],
            r.get("ow_aqi"),
            r.get("pm2_5"),
            r.get("pm10"),
            r.get("co"),
            r.get("no"),
            r.get("no2"),
            r.get("o3"),
            r.get("so2"),
            r.get("nh3"),
        )
        for r in records
    ]
    insert_sql = """
    INSERT INTO bronze.air_quality_raw (
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
    ) VALUES %s ON CONFLICT (city, observed_at) DO NOTHING
    """
    with _db_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, rows)
            log.info(
                "Inserted %s rows into RDS bronze.air_quality_raw (duplicates ignored)",
                cur.rowcount,
            )


def validate_bronze(**context):
    """
    Validate the newly loaded bronze batch incrementally.

    Checks (aligned with the original Great Expectations suite intent):
    - pm2_5 is not null
    - pm2_5 is between 0 and 1000 (sanity bound)
    - ow_aqi is between 1 and 5 (OpenWeatherMap AQI scale)
    - city is in expected list of cities
    - observed_at is not null and is a valid timestamp
    """
    ge_root = os.path.join(os.path.dirname(__file__), "..", "include", "great_expectations")
    data_context = DataContext(ge_root)

    batch_request = (
        datasource_name="datapulse_rds",
        data_connector_name="default_runtime_data_connector",
        data_asset_name="bronze_last_2h",
        runtime_parameters={
            "query": """
                SELECT * FROM bronze.air_quality_raw
                WHERE observed_at >= NOW() - INTERVAL '2 hours'
            """
        },
        batch_identifiers = {"run_id": context["run_id"]},
    )

    result = data_context.run_checkpoint(
        checkpoint_name="bronze_checkpoint",
        validations = [
            {
                "batch_request": batch_request,
                "expectation_suite_name": "bronze_air_quality_raw",
            }
        ],
    )

    if not result["success"]:
        failed = []
        for run_result in result["run_results"].values():
            for vr in run_result.get("validation_results", []).get("results", []):
                if not vr["success"]:
                    failed.append(vr["expectation_config"]["expectation_type"])
        
        raise ValueError(f"Bronze validation failed for expectations: {failed}")
    
    log.info("Bronze checkpoint passed for all expectations")


with DAG(
    dag_id="ingest_air_quality",
    default_args=DEFAULT_ARGS,
    description="Hourly: Openweather API -> S3 Bronze + RDS bronze + validation",
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
