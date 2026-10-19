"""A small JSON snapshot of the gold layer for websites (gold/web/snapshot.json).

Browsers cannot read Parquet without heavy libraries, so every hourly run also
writes this file (about 30 kB): for each capital, the forecast for the current
hour and the next 24 h, the latest observation at its linked AEMET station, and
the latest forecast accuracy. The portfolio reads it directly from the bucket.
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from .lake import Lake, existing
from .transform import sql_list

HOURS_AHEAD = 24


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cursor = connection.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _iso(value: datetime | None) -> str | None:
    # Every timestamp in the lake is UTC without a zone; say so explicitly for browsers.
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def build_web_snapshot(connection: duckdb.DuckDBPyConnection, lake: Lake, now: datetime) -> Path | None:
    """Writes gold/web/snapshot.json from the gold tables. Returns None if there is no forecast yet."""
    forecast_file = lake.gold_latest_forecast()
    if not forecast_file.exists():
        return None
    current_hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    window_end = current_hour + timedelta(hours=HOURS_AHEAD)

    forecasts = _rows(
        connection,
        f"""
        SELECT location_id, location_name, latitude, longitude, issued_at, valid_at,
               temperature_c, precipitation_mm, wind_speed_kmh, cloud_cover_pct
        FROM read_parquet({sql_list([forecast_file])})
        WHERE valid_at >= TIMESTAMP '{current_hour}' AND valid_at < TIMESTAMP '{window_end}'
        ORDER BY location_id, valid_at
        """,
    )

    observed: dict[str, dict] = {}
    today = current_hour.date()
    observation_files = existing([lake.silver_observations(today - timedelta(days=1)), lake.silver_observations(today)])
    if lake.gold_location_station().exists() and observation_files:
        for row in _rows(
            connection,
            f"""
            SELECT l.location_id, l.station_name, arg_max(o.temperature_c, o.observed_at) AS temperature_c,
                   max(o.observed_at) AS observed_at
            FROM read_parquet({sql_list([lake.gold_location_station()])}) l
            JOIN read_parquet({sql_list(observation_files)}) o USING (station_id)
            WHERE o.temperature_c IS NOT NULL
            GROUP BY l.location_id, l.station_name
            """,
        ):
            observed[row["location_id"]] = row

    capitals: dict[str, dict] = {}
    for row in forecasts:
        capital = capitals.setdefault(
            row["location_id"],
            {
                "id": row["location_id"],
                "name": row["location_name"],
                "lat": _round(row["latitude"], 4),
                "lon": _round(row["longitude"], 4),
                "issued_at": _iso(row["issued_at"]),
                "temperature_c": _round(row["temperature_c"]),
                "wind_kmh": _round(row["wind_speed_kmh"]),
                "cloud_pct": _round(row["cloud_cover_pct"], 0),
                "precipitation_24h_mm": 0.0,
                "next_24h_temperature_c": [],
            },
        )
        capital["next_24h_temperature_c"].append(_round(row["temperature_c"]))
        capital["precipitation_24h_mm"] = _round(capital["precipitation_24h_mm"] + (row["precipitation_mm"] or 0))
    for capital in capitals.values():
        observation = observed.get(capital["id"])
        capital["observed"] = (
            {
                "temperature_c": _round(observation["temperature_c"]),
                "observed_at": _iso(observation["observed_at"]),
                "station": observation["station_name"],
            }
            if observation
            else None
        )

    snapshot = {
        "generated_at": _iso(now.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)),
        "forecast_issued_at": max((c["issued_at"] for c in capitals.values()), default=None),
        "source": "Open-Meteo forecasts (CC BY 4.0) and AEMET OpenData observations",
        "skill": _latest_skill(connection, lake, today),
        "capitals": sorted(capitals.values(), key=lambda c: c["name"]),
    }
    output = lake.gold_web_snapshot()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(output)
    return output


def _latest_skill(connection: duckdb.DuckDBPyConnection, lake: Lake, today: date) -> dict | None:
    """Mean absolute temperature error across capitals: yesterday (a full day) if available, else today."""
    for day in (today - timedelta(days=1), today):
        summary = lake.gold_partition("daily_summary", day)
        if not summary.exists():
            continue
        row = _rows(
            connection,
            f"""
            SELECT count(*) AS capitals,
                   avg(temperature_mae_lead_1_6h) AS lead_1_6h,
                   avg(temperature_mae_lead_7_24h) AS lead_7_24h,
                   avg(temperature_mae_lead_25_48h) AS lead_25_48h,
                   avg(temperature_mae_lead_49_72h) AS lead_49_72h
            FROM read_parquet({sql_list([summary])})
            """,
        )[0]
        return {
            "date": day.isoformat(),
            "capitals": row["capitals"],
            "temperature_mae_c": {
                key: _round(row[key], 2) for key in ("lead_1_6h", "lead_7_24h", "lead_25_48h", "lead_49_72h")
            },
        }
    return None
