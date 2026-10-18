-- GOLD · forecast_vs_observed
-- Every forecast made for an observed hour, next to what actually happened.
-- One row per capital, observed hour and forecast lead time (0-72 h). error = forecast - observed.
-- This is the basis for measuring forecast skill and for training models that correct or beat it.
-- Params: {date}, {observation_files}, {forecast_files}, {location_station_file}
WITH links AS (
    SELECT location_id, station_id FROM read_parquet({location_station_file})
),
observed AS (
    SELECT l.location_id, o.*
    FROM read_parquet({observation_files}) o
    JOIN links l USING (station_id)
    WHERE CAST(o.observed_at AS DATE) = DATE '{date}'
),
forecast AS (
    SELECT * FROM read_parquet({forecast_files})
    WHERE CAST(valid_at AS DATE) = DATE '{date}'
)
SELECT
    o.location_id,
    o.station_id,
    o.observed_at AS valid_at,
    f.issued_at,
    f.lead_hours,
    f.temperature_c AS forecast_temperature_c,
    o.temperature_c AS observed_temperature_c,
    f.temperature_c - o.temperature_c AS error_temperature_c,
    f.relative_humidity_pct AS forecast_relative_humidity_pct,
    o.relative_humidity_pct AS observed_relative_humidity_pct,
    f.relative_humidity_pct - o.relative_humidity_pct AS error_relative_humidity_pct,
    f.precipitation_mm AS forecast_precipitation_mm,
    o.precipitation_mm AS observed_precipitation_mm,
    f.pressure_msl_hpa AS forecast_pressure_msl_hpa,
    o.pressure_msl_hpa AS observed_pressure_msl_hpa,
    f.pressure_msl_hpa - o.pressure_msl_hpa AS error_pressure_msl_hpa,
    f.wind_speed_kmh AS forecast_wind_speed_kmh,
    o.wind_speed_kmh AS observed_wind_speed_kmh,
    f.wind_speed_kmh - o.wind_speed_kmh AS error_wind_speed_kmh
FROM observed o
JOIN forecast f ON f.location_id = o.location_id AND f.valid_at = o.observed_at
ORDER BY o.location_id, valid_at, f.lead_hours
