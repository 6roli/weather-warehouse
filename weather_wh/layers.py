"""Builds silver and gold for given days from whatever is in the local lake.

Every builder is idempotent: running it twice gives the same files, so a failed
or repeated hourly run is harmless.
"""

import logging
from datetime import date, timedelta
from pathlib import Path

import duckdb

from .lake import Lake, existing
from .locations import SEED_FILE
from .sources import aemet, open_meteo
from .transform import run_to_parquet, sql_list

log = logging.getLogger(__name__)


def _locations_file() -> str:
    return "'" + SEED_FILE.resolve().as_posix().replace("'", "''") + "'"


def build_silver(connection: duckdb.DuckDBPyConnection, lake: Lake, days: list[date]) -> list[Path]:
    written: list[Path] = []
    for day in days:
        forecast_bronze = lake.bronze_files(open_meteo.SOURCE, [day])
        if forecast_bronze:
            output = lake.silver_forecasts(day)
            rows = run_to_parquet(connection, "silver_forecasts", output, bronze_files=sql_list(forecast_bronze))
            log.info("silver forecasts %s: %d rows", day, rows)
            written.append(output)

        # Observations of a day can arrive in downloads made that day or the next (24 h window).
        observation_bronze = lake.bronze_files(aemet.SOURCE, [day, day + timedelta(days=1)])
        if observation_bronze:
            output = lake.silver_observations(day)
            rows = run_to_parquet(
                connection, "silver_observations", output, bronze_files=sql_list(observation_bronze), date=day.isoformat()
            )
            log.info("silver observations %s: %d rows", day, rows)
            written.append(output)

    # Station list from the most recent AEMET downloads.
    latest_days = sorted(set(days))[-2:]
    station_bronze = lake.bronze_files(aemet.SOURCE, latest_days)
    if station_bronze:
        output = lake.silver_stations()
        rows = run_to_parquet(connection, "silver_stations", output, bronze_files=sql_list(station_bronze))
        log.info("silver stations: %d rows", rows)
        written.append(output)
    return written


def build_gold(connection: duckdb.DuckDBPyConnection, lake: Lake, days: list[date], today: date) -> list[Path]:
    written: list[Path] = []

    # Latest forecast needs only forecasts, so it exists even before AEMET is connected.
    forecast_files = existing([lake.silver_forecasts(today), lake.silver_forecasts(today - timedelta(days=1))])
    if forecast_files:
        output = lake.gold_latest_forecast()
        rows = run_to_parquet(
            connection, "gold_latest_forecast", output, forecast_files=sql_list(forecast_files), locations_file=_locations_file()
        )
        log.info("gold latest_forecast: %d rows", rows)
        written.append(output)

    if not lake.silver_stations().exists():
        log.info("No AEMET stations yet: skipping observation-based gold tables")
        return written

    links = lake.gold_location_station()
    rows = run_to_parquet(
        connection,
        "gold_location_station",
        links,
        locations_file=_locations_file(),
        stations_file=sql_list([lake.silver_stations()]),
    )
    log.info("gold location_station: %d capitals linked to a station", rows)
    written.append(links)

    for day in days:
        observations = existing([lake.silver_observations(day)])
        # Forecasts for this day were issued up to 3 days before (72 h lead).
        forecasts = existing([lake.silver_forecasts(day - timedelta(days=offset)) for offset in range(4)])
        if not observations or not forecasts:
            continue
        params = {"date": day.isoformat(), "forecast_files": sql_list(forecasts), "location_station_file": sql_list([links])}

        fvo = lake.gold_partition("forecast_vs_observed", day)
        rows = run_to_parquet(
            connection, "gold_forecast_vs_observed", fvo, observation_files=sql_list(observations), **params
        )
        log.info("gold forecast_vs_observed %s: %d rows", day, rows)
        written.append(fvo)

        features = lake.gold_partition("training_features", day)
        feature_observations = existing([lake.silver_observations(day - timedelta(days=1)), lake.silver_observations(day)])
        rows = run_to_parquet(
            connection, "gold_training_features", features, observation_files=sql_list(feature_observations), **params
        )
        log.info("gold training_features %s: %d rows", day, rows)
        written.append(features)

        summary = lake.gold_partition("daily_summary", day)
        rows = run_to_parquet(
            connection, "gold_daily_summary", summary, date=day.isoformat(), forecast_vs_observed_file=sql_list([fvo])
        )
        log.info("gold daily_summary %s: %d rows", day, rows)
        written.append(summary)
    return written
