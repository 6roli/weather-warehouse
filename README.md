# Weather warehouse

An hourly weather data warehouse for Spain's 52 provincial capitals, built as a **medallion architecture**
(bronze → silver → gold) on DuckDB and Parquet. It stores what was **forecast** and what was **observed**, hour
by hour, so future apps can measure forecast skill and train machine-learning and deep-learning models to
predict the weather.

| | |
|---|---|
| Data | Open-Meteo forecasts (72 h ahead) + AEMET station observations, every hour |
| Storage | Parquet in a public Hugging Face Storage Bucket (`hf://buckets/6roli/weather-warehouse`) |
| Engine | DuckDB (SQL files, one per table) |
| Schedule | GitHub Actions, every hour at minute 25 |
| Cost | €0 |

## Why hourly, and why forecasts *and* observations

Past forecasts are hard to get afterwards: once a new forecast is published, the old one is gone. Saving every
forecast together with what actually happened builds, from day one, the dataset needed to:

- measure how accurate forecasts are at each lead time (1 h, 6 h, 24 h, 72 h ahead);
- train models that correct the forecast (post-processing) or predict directly from observations;
- compare any future model against a real baseline.

## Architecture

```
                 GitHub Actions — every hour
                          │
     ┌────────────────────┼─────────────────────┐
     ▼                                          ▼
 Open-Meteo forecast API                AEMET OpenData
 52 capitals × 72 h × 10 variables      ~900 stations, last 24 h
     │                                          │
     ▼                                          ▼
 BRONZE   raw responses, gzipped JSON, never modified
          bronze/source=…/date=YYYY-MM-DD/hour=HH.json.gz
     │
     ▼
 SILVER   cleaned, typed, deduplicated, units harmonised (Parquet, one file per day)
          forecasts_hourly · observations_hourly · stations
     │
     ▼
 GOLD     combined, ready for apps and machine learning
          latest_forecast · location_station · forecast_vs_observed · training_features · daily_summary
     │
     ▼
 Hugging Face Storage Bucket (public) ──► future apps, notebooks, ML training (read with DuckDB/pandas)
```

Every hourly run downloads only the partitions it needs, rebuilds **today and yesterday**, and uploads the
changed files. All steps are idempotent: re-running an hour gives the same result.

## Tables

### Silver

| Table | Grain | Main columns |
|---|---|---|
| `forecasts_hourly` | capital × issue hour × forecast hour | `issued_at`, `valid_at`, `lead_hours`, temperature, humidity, dew point, precipitation, pressure, cloud cover, wind speed/direction/gusts, solar radiation |
| `observations_hourly` | AEMET station × hour | `observed_at`, temperature, humidity, dew point, precipitation, pressure, wind speed/direction/gusts (km/h), visibility |
| `stations` | AEMET station | name, latitude, longitude, altitude |

Rules applied in silver: timestamps in UTC; AEMET wind converted from m/s to km/h; physically impossible values
(e.g. 99 °C, 150 % humidity) set to NULL; when the same hour was downloaded several times, the newest download wins.

### Gold

| Table | Purpose |
|---|---|
| `latest_forecast` | Newest 72-hour forecast per capital with name and position — for apps and dashboards |
| `location_station` | Nearest AEMET station (≤ 25 km) to each capital, to compare forecasts with observations |
| `forecast_vs_observed` | Every forecast made for an observed hour next to the observation, with the error, per lead time |
| `training_features` | One row per capital-hour: observed targets + lags (1, 3, 6, 24 h), 24 h aggregates, forecasts issued 1/6/24 h earlier, cyclical calendar features |
| `daily_summary` | Daily min/max/mean temperature, precipitation, max wind, and forecast error (MAE) by lead-time band |

## Reading the data

```python
import duckdb

duckdb.sql("""
    SELECT location_name, valid_at, temperature_c, precipitation_mm
    FROM 'hf://buckets/6roli/weather-warehouse/gold/latest_forecast/data.parquet'
    WHERE location_id = 'madrid'
""").show()
```

## Run locally (VS Code)

Requirements: Python 3.12+ and Git.

```bash
git clone https://github.com/6roli/weather-warehouse.git
cd weather-warehouse
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
weather-wh hourly               # writes to ./data (Open-Meteo only, unless keys are set)
weather-wh status               # what the local lake contains
python -m pytest                # tests, no network needed
```

| Command | Purpose |
|---|---|
| `weather-wh hourly` | Fetch all sources into bronze, rebuild silver and gold for today and yesterday |
| `weather-wh rebuild --days 7` | Rebuild silver and gold from bronze for the last 7 days (no fetching) — use after changing SQL |
| `weather-wh status [--remote]` | Markdown report of the local lake, or of the bucket |

To change a table, edit its file in `weather_wh/sql/` (one `SELECT` per table) and run `weather-wh rebuild`.

## Configuration

Copy `.env.example` to `.env` for local runs. In GitHub: *Settings → Secrets and variables → Actions*.

| Name | Where | Purpose |
|---|---|---|
| `AEMET_API_KEY` | Secret | AEMET OpenData key (free, by e-mail at https://opendata.aemet.es/centrodedescargas/altaUsuario). Without it, only forecasts are collected |
| `HF_TOKEN` | Secret | Hugging Face token with write access to the bucket |
| `HF_BUCKET` | Variable | e.g. `6roli/weather-warehouse` |

## Sources and licences

| Source | Licence and conditions | Attribution |
|---|---|---|
| [Open-Meteo](https://open-meteo.com) forecast API | Data CC BY 4.0. Free API for non-commercial use, < 10,000 calls/day (this project: ~1,250) | "Weather data by Open-Meteo.com" |
| [AEMET OpenData](https://opendata.aemet.es) | Free reuse citing AEMET as the source; data provided as is | "Fuente: AEMET" |
| Capital coordinates | Open-Meteo geocoding (GeoNames, CC BY 4.0), stored in `seeds/locations.csv` | GeoNames |

Anyone reusing data from the bucket must keep these attributions.

## Costs

| Item | Plan | Cost |
|---|---|---|
| Scheduling | GitHub Actions, public repository | €0 (unlimited minutes) |
| Storage | Hugging Face Storage Bucket, public | €0 (free public storage; a few GB per year expected) |
| APIs | Open-Meteo (free non-commercial), AEMET OpenData | €0 |

GitHub disables scheduled workflows in public repositories after 60 days without activity; the monthly
`status.yml` workflow commits `STATUS.md`, which keeps the schedule alive and documents the data.

## Limitations

- `issued_at` is the hour the forecast was downloaded. Open-Meteo does not expose the model run time, so the
  underlying model run can be a few hours older.
- Observations come from the nearest AEMET station within 25 km of each capital, which may not represent the
  whole city (altitude, coast, urban heat).
- The AEMET field mapping follows the AEMET OpenData documentation and is validated with synthetic tests;
  it will be checked against the first real downloads once the API key is configured.
- GitHub's scheduler can start runs late or skip some during busy periods; gaps are visible as missing hours.

## Roadmap

1. Connect AEMET and the Hugging Face bucket (keys pending).
2. Backfill several years of hourly reanalysis (ERA5 via Open-Meteo Historical API) for model training.
3. A small dashboard on the portfolio reading the gold tables.
4. A separate app with ML/DL models (e.g. gradient boosting, then sequence models) trained on `training_features`,
   evaluated against the Open-Meteo baseline in `forecast_vs_observed`.
5. Optionally move the SQL models to dbt once the number of tables grows.
