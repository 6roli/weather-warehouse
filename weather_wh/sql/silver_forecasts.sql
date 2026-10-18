-- SILVER · forecasts_hourly
-- One row per location, issue hour and forecast hour, from Open-Meteo bronze files.
-- issued_at is the hour the forecast was downloaded (Open-Meteo does not expose the model run time).
-- Params: {bronze_files}
WITH raw AS (
    SELECT
        utc_ts(fetched_at) AS fetched_at,
        unnest(CAST(json_extract(context, '$.location_ids') AS VARCHAR[])) AS location_id,
        unnest(CAST(payload AS JSON[])) AS p
    FROM read_json({bronze_files}, columns = {fetched_at: 'VARCHAR', context: 'JSON', payload: 'JSON'},
                   maximum_object_size = 134217728)
),
hours AS (
    SELECT
        location_id,
        fetched_at,
        unnest(CAST(p -> '$.hourly.time' AS VARCHAR[])) AS valid_time,
        unnest(CAST(p -> '$.hourly.temperature_2m' AS DOUBLE[])) AS temperature_c,
        unnest(CAST(p -> '$.hourly.relative_humidity_2m' AS DOUBLE[])) AS relative_humidity_pct,
        unnest(CAST(p -> '$.hourly.dew_point_2m' AS DOUBLE[])) AS dew_point_c,
        unnest(CAST(p -> '$.hourly.precipitation' AS DOUBLE[])) AS precipitation_mm,
        unnest(CAST(p -> '$.hourly.pressure_msl' AS DOUBLE[])) AS pressure_msl_hpa,
        unnest(CAST(p -> '$.hourly.cloud_cover' AS DOUBLE[])) AS cloud_cover_pct,
        unnest(CAST(p -> '$.hourly.wind_speed_10m' AS DOUBLE[])) AS wind_speed_kmh,
        unnest(CAST(p -> '$.hourly.wind_direction_10m' AS DOUBLE[])) AS wind_direction_deg,
        unnest(CAST(p -> '$.hourly.wind_gusts_10m' AS DOUBLE[])) AS wind_gusts_kmh,
        unnest(CAST(p -> '$.hourly.shortwave_radiation' AS DOUBLE[])) AS shortwave_radiation_wm2
    FROM raw
)
SELECT
    location_id,
    date_trunc('hour', fetched_at) AS issued_at,
    utc_ts(valid_time) AS valid_at,
    date_diff('hour', date_trunc('hour', fetched_at), utc_ts(valid_time)) AS lead_hours,
    temperature_c, relative_humidity_pct, dew_point_c, precipitation_mm, pressure_msl_hpa,
    cloud_cover_pct, wind_speed_kmh, wind_direction_deg, wind_gusts_kmh, shortwave_radiation_wm2,
    'open-meteo:best_match' AS model,
    fetched_at
FROM hours
WHERE utc_ts(valid_time) >= date_trunc('hour', fetched_at)
-- If an hour was fetched twice, keep the latest download.
QUALIFY row_number() OVER (PARTITION BY location_id, issued_at, valid_at ORDER BY fetched_at DESC) = 1
ORDER BY location_id, issued_at, valid_at
