# datapulse-pipeline

Hourly air quality monitoring for Nepal — Kathmandu, Pokhara, Biratnagar, Dhangadhi.

Pulls PM2.5 and other pollutants from the OpenWeather API; pipes it through S3 → RDS → dbt; surfaces the results in a Streamlit dashboard.

## What it answers

- What's the current PM2.5 in each city?
- Which city has the worst air over time?
- How often do cities exceed WHO daily limits (45 µg/m³)?

## Stack

- **Orchestration:** Airflow (runs hourly on EC2)
- **Storage:** S3 (bronze), RDS PostgreSQL (bronze → silver → gold)
- **Transform:** dbt
- **Quality:** Great Expectations
- **Frontend:** Streamlit

## Quick start

```bash
cp .env.example .env   # fill in your keys
make up                # start Airflow locally via Docker Compose
make init-rds          # initialize RDS schema
```

Streamlit dashboard: `streamlit run streamlit/app.py`

## Structure

```
dags/                  # Airflow DAGs
dbt/                   # dbt models (bronze → gold)
streamlit/             # Dashboard app
great_expectations/    # Data quality checks
infra/                 # RDS init, EC2 setup
include/               # Shared Python modules
```
