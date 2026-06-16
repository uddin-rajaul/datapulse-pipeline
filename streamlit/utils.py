import os
import pandas as pd


def get_connection():
    import psycopg2
    host = os.getenv("RDS_HOST")
    port = int(os.getenv("RDS_PORT", "5432"))
    dbname = os.getenv("RDS_DB")
    user = os.getenv("RDS_READER_USER")
    password = os.getenv("RDS_READER_PASSWORD")
    if not all([host, dbname, user, password]):
        return None
    return psycopg2.connect(
        host=host, port=port, dbname=dbname,
        user=user, password=password,
        connect_timeout=5,
    )


def query_df(query, params=None):
    try:
        conn = get_connection()
        if conn is None:
            return pd.DataFrame()
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def check_db():
    conn = get_connection()
    if conn is None:
        return False
    conn.close()
    return True


def get_date_range():
    df = query_df("""
        SELECT min(observed_date) as start_date,
               max(observed_date) as end_date
        FROM gold.city_comparison
    """)
    if df.empty or df.iloc[0]["start_date"] is None:
        return None, None
    return df.iloc[0]["start_date"], df.iloc[0]["end_date"]


def get_latest_readings():
    return query_df("""
        SELECT DISTINCT ON (city)
            city, observed_date, avg_pm25, max_pm25, avg_aqi
        FROM gold.daily_city_avg
        ORDER BY city, observed_date DESC
    """)


def get_time_series(cities, start_date, end_date):
    placeholders = ", ".join([f"'{c}'" for c in cities])
    return query_df(f"""
        SELECT city, observed_date, avg_pm25, max_pm25,
               rolling_7day_avg_pm25, exceeds_daily_who
        FROM gold.city_comparison
        WHERE city IN ({placeholders})
          AND observed_date BETWEEN %(start)s AND %(end)s
        ORDER BY city, observed_date
    """, {"start": start_date, "end": end_date})


def get_comparison_data(start_date, end_date):
    return query_df("""
        SELECT city,
               count(*) as total_days,
               round(avg(avg_pm25)::numeric, 2) as mean_pm25,
               round(max(max_pm25)::numeric, 2) as max_pm25,
               count(*) filter (where exceeds_daily_who) as who_breach_days,
               round(
                   avg(avg_pm25) filter (where avg_pm25 > 45)::numeric, 2
               ) as mean_breach_pm25
        FROM gold.city_comparison
        WHERE observed_date BETWEEN %(start)s AND %(end)s
        GROUP BY city
        ORDER BY city
    """, {"start": start_date, "end": end_date})


def get_aqi_distribution(start_date, end_date):
    return query_df("""
        SELECT city, aqi_label, sum(reading_count)::int as total_readings
        FROM gold.aqi_distribution
        WHERE observed_date BETWEEN %(start)s AND %(end)s
        GROUP BY city, aqi_label
        ORDER BY city, aqi_label
    """, {"start": start_date, "end": end_date})
