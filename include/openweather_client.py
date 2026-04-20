import requests
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CITIES = {
    "kathmandu": {"lat": 27.7172, "lon": 85.3240},
    "pokhara": {"lat": 28.2096, "lon": 83.9856},
    "biratnagar": {"lat": 26.4525, "lon": 87.2718},
    "dhangadhi": {"lat": 28.6833, "lon": 80.5833},
}

BASE_URL = "http://api.openweathermap.org/data/2.5"

def fetch_air_quality_data(city: str, api_key: str) -> dict:
    """
    Fetch air quality data for a city from OpenWeatherMap API.
    Returns a flat, normalized dict ready for s3 storage.
    Raises on HTTP errors or missing data.
    """
    if city not in CITIES:
        raise ValueError(f"Unknown city: {city}. Must be one of {list(CITIES.keys())}")
    
    coords = CITIES[city]

    response = requests.get(
        f"{BASE_URL}/air_pollution",
        params={
            "lat": coords["lat"],
            "lon": coords["lon"],
            "appid": api_key
        },
        timeout=10
    )

    response.raise_for_status()
    raw = response.json()

    record = raw['list'][0]
    components = record['components']

    if components['pm2_5'] is None:
        raise ValueError(f"Missing PM2.5 data for {city} at {record['dt']}")
    
    return {
        "city": city,
        "lat": coords["lat"],
        "lon": coords["lon"],
        # Timing
        "observed_at": datetime.fromtimestamp(record['dt'], tz=timezone.utc).isoformat(),
        "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
        # OpenWeatherMap AQI scale: 1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor
        "ow_aqi": record['main']['aqi'],

        # Pollutant concentrations in μg/m3
        "pm2_5": components['pm2_5'],
        "pm10": components.get('pm10'),
        "co": components.get('co'),
        "no": components.get('no'),
        "no2": components.get('no2'),
        "o3": components.get('o3'),
        "so2": components.get('so2'),
        "nh3": components.get('nh3'),
    }


def fetch_all_cities(api_key:str) -> list[dict]:
    """
    Fetch air quality data for all cities defined in CITIES.
    Returns a list of dicts, one per city.
    """
    results = []
    for city in CITIES:
        try:
            data = fetch_air_quality_data(city, api_key)
            results.append(data)
            logger.info(f"Fetched data for {city}")
        except Exception as e:
            logger.error(f"Error fetching data for {city}: {e}")
    return results

