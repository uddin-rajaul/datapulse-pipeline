import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

from utils import (
    check_db, get_date_range, get_latest_readings,
    get_time_series, get_comparison_data, get_aqi_distribution,
)

WHO_DAILY = 45
WHO_ANNUAL = 15
CITIES = ["kathmandu", "pokhara", "biratnagar", "dhangadhi"]

AQI_ORDER = ["Good", "Fair", "Moderate", "Poor", "Very Poor"]
AQI_COLORS = {
    "Good": "#00e400",
    "Fair": "#ffff00",
    "Moderate": "#ff7e00",
    "Poor": "#ff0000",
    "Very Poor": "#8f3f97",
}


def pm25_color(value):
    if value is None:
        return "#cccccc"
    if value < WHO_ANNUAL:
        return AQI_COLORS["Good"]
    if value < WHO_DAILY:
        return AQI_COLORS["Fair"]
    if value < 100:
        return AQI_COLORS["Moderate"]
    if value < 250:
        return AQI_COLORS["Poor"]
    return AQI_COLORS["Very Poor"]


def pm25_severity(value):
    if value is None:
        return "No data"
    if value < WHO_ANNUAL:
        return "Good"
    if value < WHO_DAILY:
        return "Moderate"
    if value < 100:
        return "Unhealthy for Sensitive Groups"
    if value < 250:
        return "Unhealthy"
    return "Hazardous"


def add_who_reference_lines(fig):
    fig.add_hline(
        y=WHO_DAILY, line_dash="dash", line_color="#e74c3c",
        opacity=0.6, line_width=1.5,
    )
    fig.add_annotation(
        xref="paper", y=WHO_DAILY, x=1.02,
        text="WHO daily (45)", showarrow=False,
        font=dict(size=10, color="#e74c3c"), yshift=5,
    )
    fig.add_hline(
        y=WHO_ANNUAL, line_dash="dot", line_color="#f39c12",
        opacity=0.6, line_width=1.5,
    )
    fig.add_annotation(
        xref="paper", y=WHO_ANNUAL, x=1.02,
        text="WHO annual (15)", showarrow=False,
        font=dict(size=10, color="#f39c12"), yshift=5,
    )


st.set_page_config(
    page_title="Datapulse — Nepal Air Quality",
    page_icon="🌬️",
    layout="wide",
)

st.title("🌬️ Datapulse — Nepal Air Quality")
st.markdown(
    "Monitoring PM2.5 in Kathmandu, Pokhara, Biratnagar, and Dhangadhi. "
    "Data sourced from [OpenWeather Air Pollution API](https://openweathermap.org/api/air-pollution) "
    "and loaded hourly via the datapulse pipeline."
)

if not check_db():
    st.error(
        "Cannot connect to the database. "
        "Set RDS_HOST, RDS_DB, RDS_READER_USER, and RDS_READER_PASSWORD "
        "in your .env file or environment."
    )
    st.stop()

START_DATE, END_DATE = get_date_range()
if START_DATE is None:
    st.warning("No data found in the database. The pipeline may not have run yet.")
    st.stop()

tab_overview, tab_timeseries, tab_comparison, tab_aqi = st.tabs([
    "📊 Overview", "📈 Time Series", "🏙️ City Comparison", "🎨 AQI Distribution",
])


with tab_overview:
    st.subheader("Latest Readings")

    latest = get_latest_readings()
    if not latest.empty:
        cols = st.columns(4)
        for i, (_, row) in enumerate(latest.iterrows()):
            color = pm25_color(row["avg_pm25"])
            severity = pm25_severity(row["avg_pm25"])
            with cols[i]:
                st.markdown(f"##### {row['city'].title()}")
                st.markdown(
                    f"<p style='font-size:2.5rem; font-weight:700; "
                    f"color:{color}; margin:-0.5rem 0'>{row['avg_pm25']}</p>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"µg/m³ · {severity}")
                st.caption(f"{row['observed_date']} · AQI: {row['avg_aqi']}")

        st.divider()
        st.subheader("PM2.5 by City")

        latest_sorted = latest.sort_values("avg_pm25", ascending=True)
        fig = px.bar(
            latest_sorted,
            x="city", y="avg_pm25",
            color="avg_pm25",
            color_continuous_scale=[
                (0, AQI_COLORS["Good"]),
                (0.15, AQI_COLORS["Fair"]),
                (0.45, AQI_COLORS["Moderate"]),
                (1.0, AQI_COLORS["Poor"]),
            ],
            labels={"city": "", "avg_pm25": "PM2.5 (µg/m³)"},
            text=latest_sorted["avg_pm25"].apply(lambda v: f"{v} µg/m³"),
            range_color=[0, latest_sorted["avg_pm25"].max() * 1.2],
        )
        fig.update_traces(
            textposition="outside", textfont_size=12,
            marker_line_width=0,
        )
        add_who_reference_lines(fig)
        fig.update_layout(
            height=350, margin=dict(t=30, b=10),
            xaxis_title=None, showlegend=False,
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No readings available yet.")


with tab_timeseries:
    st.subheader("PM2.5 Over Time")

    selected_cities = st.multiselect(
        "Cities", CITIES, default=CITIES[:2],
        format_func=lambda c: c.title(),
    )

    range_col1, range_col2 = st.columns(2)
    default_start = END_DATE - timedelta(days=30)
    with range_col1:
        start = st.date_input(
            "Start date", value=default_start,
            min_value=START_DATE, max_value=END_DATE,
        )
    with range_col2:
        end = st.date_input(
            "End date", value=END_DATE,
            min_value=START_DATE, max_value=END_DATE,
        )

    show_rolling = st.checkbox("Show 7-day rolling average", value=True)

    if selected_cities and start <= end:
        ts = get_time_series(selected_cities, start, end)
        if not ts.empty:
            fig = px.line(
                ts, x="observed_date", y="avg_pm25",
                color="city", line_shape="spline",
                labels={
                    "observed_date": "",
                    "avg_pm25": "PM2.5 (µg/m³)",
                    "city": "",
                },
                color_discrete_sequence=px.colors.qualifier.Set2,
            )

            if show_rolling:
                for city in selected_cities:
                    city_data = ts[ts["city"] == city]
                    fig.add_scatter(
                        x=city_data["observed_date"],
                        y=city_data["rolling_7day_avg_pm25"],
                        mode="lines",
                        line=dict(dash="dot", width=1.5),
                        name=f"{city.title()} (7d avg)",
                        opacity=0.6,
                    )

            add_who_reference_lines(fig)
            fig.update_layout(
                height=450, margin=dict(t=10, b=10),
                hovermode="x unified",
                legend=dict(
                    orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1,
                ),
            )
            st.plotly_chart(fig, use_container_width=True)

            breach_pct = (
                ts.groupby("city")["exceeds_daily_who"].mean() * 100
            ).reset_index()
            breach_pct.columns = ["city", "breach_pct"]
            breach_pct["breach_pct"] = breach_pct["breach_pct"].round(1)

            st.markdown("##### Days exceeding WHO daily guideline (45 µg/m³)")
            cols = st.columns(len(selected_cities))
            for i, (_, row) in enumerate(breach_pct.iterrows()):
                with cols[i]:
                    pct = row["breach_pct"]
                    color = "#e74c3c" if pct > 50 else "#f39c12" if pct > 20 else "#27ae60"
                    st.markdown(
                        f"<span style='font-size:1.8rem; font-weight:600; color:{color}'>"
                        f"{pct}%</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"{row['city'].title()}")
        else:
            st.info("No data for the selected filters.")
    else:
        if not selected_cities:
            st.info("Select at least one city.")
        if start > end:
            st.error("Start date must be before end date.")


with tab_comparison:
    st.subheader("City Comparison")

    cmp_col1, cmp_col2 = st.columns(2)
    cmp_default_start = END_DATE - timedelta(days=30)
    with cmp_col1:
        cmp_start = st.date_input(
            "Start date", value=cmp_default_start,
            min_value=START_DATE, max_value=END_DATE,
            key="cmp_start",
        )
    with cmp_col2:
        cmp_end = st.date_input(
            "End date", value=END_DATE,
            min_value=START_DATE, max_value=END_DATE,
            key="cmp_end",
        )

    if cmp_start <= cmp_end:
        comp = get_comparison_data(cmp_start, cmp_end)
        if not comp.empty:
            comp = comp.sort_values("mean_pm25", ascending=False)

            for _, row in comp.iterrows():
                color = pm25_color(row["mean_pm25"])
                st.markdown(
                    f"##### {row['city'].title()} "
                    f"<span style='color:{color}'>{row['mean_pm25']} µg/m³</span> avg",
                    unsafe_allow_html=True,
                )
                metric_cols = st.columns(4)
                metric_cols[0].metric("Max PM2.5", f"{row['max_pm25']} µg/m³")
                metric_cols[1].metric(
                    "WHO Breach Days",
                    f"{row['who_breach_days']} / {row['total_days']} days",
                )
                breach_ratio = (
                    row["who_breach_days"] / row["total_days"] * 100
                    if row["total_days"] > 0 else 0
                )
                metric_cols[2].metric("Breach Rate", f"{breach_ratio:.0f}%")
                m = row["mean_breach_pm25"]
                metric_cols[3].metric(
                    "Mean on Breach Days",
                    f"{m} µg/m³" if pd.notna(m) else "N/A",
                )
                st.divider()

            fig = px.bar(
                comp, x="city", y="mean_pm25",
                color="mean_pm25",
                color_continuous_scale=[
                    (0, AQI_COLORS["Good"]),
                    (0.15, AQI_COLORS["Fair"]),
                    (0.45, AQI_COLORS["Moderate"]),
                    (1.0, AQI_COLORS["Poor"]),
                ],
                labels={"city": "", "mean_pm25": "Mean PM2.5 (µg/m³)"},
                text=comp["mean_pm25"].apply(lambda v: f"{v} µg/m³"),
            )
            fig.update_traces(
                textposition="outside", textfont_size=12,
                marker_line_width=0,
            )
            add_who_reference_lines(fig)
            fig.update_layout(
                height=350, margin=dict(t=30, b=10),
                xaxis_title=None, showlegend=False,
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data for the selected date range.")
    else:
        st.error("Start date must be before end date.")


with tab_aqi:
    st.subheader("AQI Distribution")

    aqi_date_col1, aqi_date_col2 = st.columns(2)
    aqi_default_start = END_DATE - timedelta(days=30)
    with aqi_date_col1:
        aqi_start = st.date_input(
            "Start date", value=aqi_default_start,
            min_value=START_DATE, max_value=END_DATE,
            key="aqi_start",
        )
    with aqi_date_col2:
        aqi_end = st.date_input(
            "End date", value=END_DATE,
            min_value=START_DATE, max_value=END_DATE,
            key="aqi_end",
        )

    if aqi_start <= aqi_end:
        dist = get_aqi_distribution(aqi_start, aqi_end)
        if not dist.empty:
            dist["aqi_label"] = pd.Categorical(
                dist["aqi_label"], categories=AQI_ORDER, ordered=True,
            )
            pivot = dist.pivot_table(
                index="city", columns="aqi_label",
                values="total_readings", aggfunc="sum", fill_value=0,
            )
            pivot = pivot[AQI_ORDER]

            pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100
            city_order = pivot.sum(axis=1).sort_values(ascending=False).index

            fig = go.Figure()
            for level in AQI_ORDER:
                fig.add_trace(go.Bar(
                    name=level,
                    x=city_order,
                    y=pivot_pct.loc[city_order, level],
                    marker_color=AQI_COLORS[level],
                    text=pivot.loc[city_order, level].values,
                    texttemplate="%{text}",
                    textposition="inside",
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        f"{level}: %{{y:.1f}}% (%{{text}} hrs)<extra></extra>"
                    ),
                ))
            fig.update_layout(
                barmode="stack",
                height=400,
                margin=dict(t=10, b=10),
                xaxis_title=None,
                yaxis_title="Percentage of readings",
                legend=dict(
                    orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1,
                ),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("##### Raw counts by AQI level")
            pivot["Total"] = pivot.sum(axis=1)
            pivot.index = [c.title() for c in pivot.index]
            st.dataframe(
                pivot, use_container_width=True,
                column_config={
                    col: st.column_config.NumberColumn(col, format="%d")
                    for col in pivot.columns
                },
            )
        else:
            st.info("No AQI data for the selected date range.")
    else:
        st.error("Start date must be before end date.")

st.divider()
st.caption(
    "Data sourced from OpenWeather Air Pollution API. "
    "WHO reference lines: 45 µg/m³ (24-hour guideline) and 15 µg/m³ (annual guideline). "
    "Updated hourly via the datapulse pipeline."
)
