"""Open-Meteo forecast API: the hourly forecast for the next 72 hours at every location.

Free for non-commercial use without an API key (< 10,000 calls/day). One request
covers all 52 locations; Open-Meteo counts each location as one call, so the
hourly job uses about 1,250 of the 10,000 daily calls. Data licence: CC BY 4.0,
attribution "Weather data by Open-Meteo.com".
"""

import urllib.parse
from datetime import datetime

from ..bronze import BronzeRecord
from ..locations import Location
from .http import get_json

SOURCE = "open_meteo_forecast"
ENDPOINT = "https://api.open-meteo.com/v1/forecast"
FORECAST_HOURS = 72

# Open-Meteo variable → unit. Names are kept as-is in bronze and renamed in silver.
HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
]


def forecast_url(locations: list[Location]) -> str:
    params = {
        "latitude": ",".join(f"{location.latitude:.5f}" for location in locations),
        "longitude": ",".join(f"{location.longitude:.5f}" for location in locations),
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_hours": FORECAST_HOURS,
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
    }
    return f"{ENDPOINT}?{urllib.parse.urlencode(params)}"


def fetch_forecast(locations: list[Location], fetched_at: datetime) -> BronzeRecord:
    url = forecast_url(locations)
    payload = get_json(url)
    # A single location returns an object; several return a list in request order.
    results = payload if isinstance(payload, list) else [payload]
    if len(results) != len(locations):
        raise ValueError(f"Open-Meteo returned {len(results)} results for {len(locations)} locations")
    return BronzeRecord(
        source=SOURCE,
        fetched_at=fetched_at,
        request=url,
        payload=results,
        # Results come back in request order; remember which location each one is.
        context={"location_ids": [location.location_id for location in locations]},
    )
