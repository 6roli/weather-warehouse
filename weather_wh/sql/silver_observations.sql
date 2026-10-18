-- SILVER · observations_hourly
-- One row per AEMET station and observation hour. Each AEMET download covers the last 24 h,
-- so the same hour arrives up to 24 times: keep the most recent download.
-- Units: AEMET reports wind in m/s; converted to km/h to match the forecasts.
-- Params: {bronze_files}, {date}
WITH raw AS (
    SELECT utc_ts(fetched_at) AS fetched_at, unnest(CAST(payload AS JSON[])) AS o
    FROM read_json({bronze_files}, columns = {fetched_at: 'VARCHAR', payload: 'JSON'},
                   maximum_object_size = 134217728)
),
typed AS (
    SELECT
        o ->> 'idema' AS station_id,
        utc_ts(o ->> 'fint') AS observed_at,
        TRY_CAST(o ->> 'ta' AS DOUBLE) AS temperature_c,
        TRY_CAST(o ->> 'hr' AS DOUBLE) AS relative_humidity_pct,
        TRY_CAST(o ->> 'tpr' AS DOUBLE) AS dew_point_c,
        TRY_CAST(o ->> 'prec' AS DOUBLE) AS precipitation_mm,
        TRY_CAST(o ->> 'pres_nmar' AS DOUBLE) AS pressure_msl_hpa,
        TRY_CAST(o ->> 'vv' AS DOUBLE) * 3.6 AS wind_speed_kmh,
        TRY_CAST(o ->> 'dv' AS DOUBLE) AS wind_direction_deg,
        TRY_CAST(o ->> 'vmax' AS DOUBLE) * 3.6 AS wind_gusts_kmh,
        TRY_CAST(o ->> 'vis' AS DOUBLE) AS visibility_km,
        fetched_at
    FROM raw
),
latest AS (
    -- Keep the whole row from the newest download of each station-hour.
    -- (GROUP BY + arg_max instead of QUALIFY: QUALIFY on these JSON-derived columns triggers an
    -- internal error in DuckDB 1.5.6, "expression type mismatch".)
    SELECT unnest(arg_max(typed, fetched_at))
    FROM typed
    WHERE station_id IS NOT NULL AND observed_at IS NOT NULL
    GROUP BY station_id, observed_at
)
SELECT
    station_id,
    observed_at,
    -- Physically impossible values become NULL rather than poisoning models.
    CASE WHEN temperature_c BETWEEN -50 AND 60 THEN temperature_c END AS temperature_c,
    CASE WHEN relative_humidity_pct BETWEEN 0 AND 100 THEN relative_humidity_pct END AS relative_humidity_pct,
    CASE WHEN dew_point_c BETWEEN -60 AND 40 THEN dew_point_c END AS dew_point_c,
    CASE WHEN precipitation_mm BETWEEN 0 AND 300 THEN precipitation_mm END AS precipitation_mm,
    CASE WHEN pressure_msl_hpa BETWEEN 870 AND 1090 THEN pressure_msl_hpa END AS pressure_msl_hpa,
    CASE WHEN wind_speed_kmh BETWEEN 0 AND 300 THEN wind_speed_kmh END AS wind_speed_kmh,
    CASE WHEN wind_direction_deg BETWEEN 0 AND 360 THEN wind_direction_deg END AS wind_direction_deg,
    CASE WHEN wind_gusts_kmh BETWEEN 0 AND 400 THEN wind_gusts_kmh END AS wind_gusts_kmh,
    CASE WHEN visibility_km >= 0 THEN visibility_km END AS visibility_km,
    fetched_at
FROM latest
WHERE CAST(observed_at AS DATE) = DATE '{date}'
ORDER BY station_id, observed_at
