"""End-to-end tests of bronze → silver → gold on small synthetic inputs (no network).

The AEMET records use the field names of the AEMET OpenData documentation
(idema, fint, ta, hr, tpr, prec, pres_nmar, vv, dv, vmax, vis, ubi, lat, lon, alt),
with made-up station ids and values.
"""

from datetime import date, datetime, timezone

import duckdb
import pytest

from weather_wh.bronze import BronzeRecord, bronze_path, write_bronze
from weather_wh.lake import Lake
from weather_wh.layers import build_gold, build_silver
from weather_wh.locations import load_locations
from weather_wh.pipeline import status_report
from weather_wh.sources import aemet, open_meteo
from weather_wh.sources.http import redact
from weather_wh.transform import connect, render

DAY = date(2026, 10, 18)


def utc(hour: int, minute: int = 5, day: int = 18) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def forecast_payload(start_hour: int, temperatures: list[float]) -> dict:
    hours = [f"2026-10-18T{start_hour + i:02d}:00" for i in range(len(temperatures))]
    series = {name: [1.0] * len(hours) for name in open_meteo.HOURLY_VARIABLES}
    series["temperature_2m"] = temperatures
    return {"hourly": {"time": hours, **series}}


def write_forecast(lake: Lake, fetched_at: datetime, madrid: list[float], sevilla: list[float]) -> None:
    write_bronze(
        lake.root,
        BronzeRecord(
            source=open_meteo.SOURCE,
            fetched_at=fetched_at,
            request="https://api.open-meteo.com/v1/forecast?test",
            payload=[forecast_payload(fetched_at.hour, madrid), forecast_payload(fetched_at.hour, sevilla)],
            context={"location_ids": ["madrid", "sevilla"]},
        ),
    )


def observation(station: str, hour: int, ta: float, **extra) -> dict:
    record = {
        "idema": station, "fint": f"2026-10-18T{hour:02d}:00:00", "ta": ta, "hr": 60, "tpr": 5.0, "prec": 0.0,
        "pres_nmar": 1015.0, "vv": 2.0, "dv": 180, "vmax": 5.0, "vis": 20.0,
        "ubi": f"Station {station}", "lat": 40.41, "lon": -3.68, "alt": 667,
    }
    record.update(extra)
    return record


@pytest.fixture
def lake(tmp_path):
    return Lake(tmp_path)


def test_bronze_layout_and_redaction(lake):
    assert bronze_path(lake.root, "x", utc(14)).as_posix().endswith("bronze/source=x/date=2026-10-18/hour=14.json.gz")
    assert redact("https://a.b/c?api_key=SECRET&x=1") == "https://a.b/c?api_key=***&x=1"


def test_render_fills_params_and_leaves_struct_literals():
    sql = render("silver_forecasts", {"bronze_files": "['f.json.gz']"})
    assert "['f.json.gz']" in sql and "{fetched_at: 'VARCHAR'" in sql
    with pytest.raises(KeyError, match="bronze_files"):
        render("silver_forecasts", {})


def test_silver_forecasts_dedupes_and_computes_lead_time(lake):
    write_forecast(lake, utc(12), madrid=[10, 11, 12], sevilla=[20, 21, 22])
    write_forecast(lake, utc(12, 40), madrid=[15, 16, 17], sevilla=[25, 26, 27])  # same hour, newer download
    build_silver(connect(), lake, [DAY])
    rows = duckdb.sql(
        f"SELECT location_id, valid_at, lead_hours, temperature_c FROM '{lake.silver_forecasts(DAY).as_posix()}' ORDER BY 1, 2"
    ).fetchall()
    assert len(rows) == 6  # 2 locations x 3 hours, duplicates removed
    assert rows[0] == ("madrid", datetime(2026, 10, 18, 12), 0, 15.0)  # newest download wins
    assert [r[2] for r in rows[:3]] == [0, 1, 2]


def test_silver_observations_keep_latest_convert_units_and_reject_impossible(lake):
    write_bronze(lake.root, BronzeRecord(aemet.SOURCE, utc(13), "x", [observation("T1", 12, 14.0)]))
    write_bronze(
        lake.root,
        BronzeRecord(aemet.SOURCE, utc(14), "x", [observation("T1", 12, 14.5), observation("T1", 13, 99.0, hr=150)]),
    )
    build_silver(connect(), lake, [DAY])
    rows = duckdb.sql(
        f"SELECT observed_at, temperature_c, relative_humidity_pct, wind_speed_kmh "
        f"FROM '{lake.silver_observations(DAY).as_posix()}' ORDER BY 1"
    ).fetchall()
    assert rows[0] == (datetime(2026, 10, 18, 12), 14.5, 60.0, pytest.approx(7.2))  # latest download, m/s → km/h
    assert rows[1][1] is None and rows[1][2] is None  # 99 °C and 150 % are impossible


def test_gold_tables_combine_forecasts_and_observations(lake):
    # Forecast issued at 10:00 for 10:00-13:00; observations at 12:00 and 13:00 near Madrid.
    write_forecast(lake, utc(10), madrid=[9, 10, 11, 12], sevilla=[20, 20, 20, 20])
    stations = [observation("NEAR", 12, 10.0), observation("NEAR", 13, 13.0),
                observation("FAR", 12, 30.0, lat=43.0, lon=-8.0)]
    write_bronze(lake.root, BronzeRecord(aemet.SOURCE, utc(14), "x", stations))

    connection = connect()
    build_silver(connection, lake, [DAY])
    build_gold(connection, lake, [DAY], today=DAY)

    links = duckdb.sql(f"SELECT location_id, station_id FROM '{lake.gold_location_station().as_posix()}'").fetchall()
    assert links == [("madrid", "NEAR")]  # Sevilla has no station within 25 km in this test

    fvo = duckdb.sql(
        f"SELECT valid_at, lead_hours, forecast_temperature_c, observed_temperature_c, error_temperature_c "
        f"FROM '{lake.gold_partition('forecast_vs_observed', DAY).as_posix()}' ORDER BY valid_at"
    ).fetchall()
    assert fvo == [(datetime(2026, 10, 18, 12), 2, 11.0, 10.0, 1.0), (datetime(2026, 10, 18, 13), 3, 12.0, 13.0, -1.0)]

    features = duckdb.sql(
        f"SELECT valid_at, target_temperature_c, temperature_lag_1h, hour_utc "
        f"FROM '{lake.gold_partition('training_features', DAY).as_posix()}' ORDER BY valid_at"
    ).fetchall()
    assert features[1] == (datetime(2026, 10, 18, 13), 13.0, 10.0, 13)

    summary = duckdb.sql(
        f"SELECT observed_hours, temperature_min_c, temperature_max_c, temperature_mae_lead_1_6h "
        f"FROM '{lake.gold_partition('daily_summary', DAY).as_posix()}'"
    ).fetchall()
    assert summary == [(2, 10.0, 13.0, 1.0)]

    latest = duckdb.sql(f"SELECT count(*), any_value(location_name) FROM '{lake.gold_latest_forecast().as_posix()}' WHERE location_id = 'madrid'").fetchone()
    assert latest == (4, "Madrid")


def test_status_report_lists_tables(lake):
    write_forecast(lake, utc(12), madrid=[10], sevilla=[20])
    build_silver(connect(), lake, [DAY])
    report = status_report(lake)
    assert "| silver | forecasts_hourly | 1 | 2 |" in report


def test_seed_has_52_unique_capitals():
    locations = load_locations()
    assert len(locations) == 52
    assert all(27 < l.latitude < 44 and -19 < l.longitude < 5 for l in locations)  # Spain incl. Canaries


def test_package_ships_its_data_files():
    """Regression: the seed lived outside the package, so `pip install .` (as in GitHub Actions) lost it."""
    import tomllib
    from pathlib import Path

    import weather_wh
    from weather_wh.locations import SEED_FILE
    from weather_wh.transform import SQL_DIR

    package_dir = Path(weather_wh.__file__).resolve().parent
    assert SEED_FILE.is_relative_to(package_dir) and SQL_DIR.is_relative_to(package_dir)
    config = tomllib.loads((package_dir.parent / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = config["tool"]["setuptools"]["package-data"]["weather_wh"]
    assert "seeds/*.csv" in shipped and "sql/*.sql" in shipped
