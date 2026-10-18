-- GOLD · latest_forecast
-- The most recent 72-hour forecast for each capital, with its name and position.
-- Ready for an app or a dashboard; replaced every hour.
-- Params: {forecast_files}, {locations_file}
WITH forecast AS (
    SELECT * FROM read_parquet({forecast_files})
),
latest AS (
    SELECT location_id, max(issued_at) AS issued_at FROM forecast GROUP BY location_id
)
SELECT
    f.location_id, l.name AS location_name, l.province, l.latitude, l.longitude,
    f.issued_at, f.valid_at, f.lead_hours,
    f.temperature_c, f.relative_humidity_pct, f.dew_point_c, f.precipitation_mm, f.pressure_msl_hpa,
    f.cloud_cover_pct, f.wind_speed_kmh, f.wind_direction_deg, f.wind_gusts_kmh, f.shortwave_radiation_wm2
FROM forecast f
JOIN latest USING (location_id, issued_at)
JOIN read_csv({locations_file}, header = true) l USING (location_id)
ORDER BY f.location_id, f.valid_at
