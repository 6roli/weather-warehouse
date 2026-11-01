# Data warehouse status

Generated 2026-11-01 12:44 UTC from `hf://buckets/groli/weather-warehouse`.

| Layer | Table | Files | Size (MB) | First day | Last day |
|---|---|---|---|---|---|
| bronze | source=aemet_observations | 311 | 160.0 | 2026-10-18 | 2026-11-01 |
| bronze | source=open_meteo_forecast | 310 | 16.4 | 2026-10-18 | 2026-11-01 |
| gold | daily_summary | 15 | 0.1 | 2026-10-18 | 2026-11-01 |
| gold | forecast_vs_observed | 15 | 5.3 | 2026-10-18 | 2026-11-01 |
| gold | latest_forecast | 1 | 0.0 | - | - |
| gold | location_station | 1 | 0.0 | - | - |
| gold | training_features | 15 | 0.6 | 2026-10-18 | 2026-11-01 |
| silver | forecasts_hourly | 15 | 9.1 | 2026-10-18 | 2026-11-01 |
| silver | observations_hourly | 16 | 1.7 | 2026-10-17 | 2026-11-01 |
| silver | stations | 1 | 0.0 | - | - |

