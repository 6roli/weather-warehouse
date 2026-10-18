-- GOLD · training_features
-- One row per capital and observed hour, ready for machine learning:
--   targets   = what was observed at that hour
--   features  = what was known before it: past observations (lags, 24 h aggregates),
--               the forecasts issued 1, 6 and 24 h earlier, and calendar signals.
-- Lags use the hour before the target (a 1-hour-ahead setting); models for longer horizons
-- should shift features accordingly (every raw hour is available in silver).
-- Params: {date}, {observation_files} (target day and the day before), {forecast_files}, {location_station_file}
WITH links AS (
    SELECT location_id, station_id FROM read_parquet({location_station_file})
),
observed AS (
    SELECT
        l.location_id,
        o.observed_at,
        o.temperature_c, o.relative_humidity_pct, o.pressure_msl_hpa, o.wind_speed_kmh, o.precipitation_mm,
        avg(o.temperature_c) OVER prev_24h AS temperature_mean_prev_24h,
        sum(o.precipitation_mm) OVER prev_24h AS precipitation_sum_prev_24h,
        avg(o.pressure_msl_hpa) OVER prev_24h AS pressure_mean_prev_24h
    FROM read_parquet({observation_files}) o
    JOIN links l USING (station_id)
    WINDOW prev_24h AS (
        PARTITION BY l.location_id ORDER BY o.observed_at
        RANGE BETWEEN INTERVAL 24 HOURS PRECEDING AND INTERVAL 1 HOUR PRECEDING
    )
),
forecast AS (
    SELECT location_id, valid_at, lead_hours, temperature_c, precipitation_mm, wind_speed_kmh
    FROM read_parquet({forecast_files})
    WHERE lead_hours IN (1, 6, 24)
)
SELECT
    t.location_id,
    t.observed_at AS valid_at,
    -- targets
    t.temperature_c AS target_temperature_c,
    t.precipitation_mm AS target_precipitation_mm,
    t.wind_speed_kmh AS target_wind_speed_kmh,
    -- past observations
    lag1.temperature_c AS temperature_lag_1h,
    lag3.temperature_c AS temperature_lag_3h,
    lag6.temperature_c AS temperature_lag_6h,
    lag24.temperature_c AS temperature_lag_24h,
    lag1.relative_humidity_pct AS relative_humidity_lag_1h,
    lag1.pressure_msl_hpa AS pressure_lag_1h,
    lag1.pressure_msl_hpa - lag6.pressure_msl_hpa AS pressure_change_6h,
    lag1.wind_speed_kmh AS wind_speed_lag_1h,
    t.temperature_mean_prev_24h,
    t.precipitation_sum_prev_24h,
    t.pressure_mean_prev_24h,
    -- forecasts made before the target hour
    f1.temperature_c AS forecast_temperature_lead_1h,
    f6.temperature_c AS forecast_temperature_lead_6h,
    f24.temperature_c AS forecast_temperature_lead_24h,
    f1.precipitation_mm AS forecast_precipitation_lead_1h,
    f1.wind_speed_kmh AS forecast_wind_speed_lead_1h,
    -- calendar, cyclically encoded so 23:00 is close to 00:00 and 31 Dec close to 1 Jan
    hour(t.observed_at) AS hour_utc,
    sin(2 * pi() * hour(t.observed_at) / 24) AS hour_sin,
    cos(2 * pi() * hour(t.observed_at) / 24) AS hour_cos,
    sin(2 * pi() * dayofyear(t.observed_at) / 365.25) AS day_of_year_sin,
    cos(2 * pi() * dayofyear(t.observed_at) / 365.25) AS day_of_year_cos
FROM observed t
LEFT JOIN observed lag1 ON lag1.location_id = t.location_id AND lag1.observed_at = t.observed_at - INTERVAL 1 HOUR
LEFT JOIN observed lag3 ON lag3.location_id = t.location_id AND lag3.observed_at = t.observed_at - INTERVAL 3 HOUR
LEFT JOIN observed lag6 ON lag6.location_id = t.location_id AND lag6.observed_at = t.observed_at - INTERVAL 6 HOUR
LEFT JOIN observed lag24 ON lag24.location_id = t.location_id AND lag24.observed_at = t.observed_at - INTERVAL 24 HOUR
LEFT JOIN forecast f1 ON f1.location_id = t.location_id AND f1.valid_at = t.observed_at AND f1.lead_hours = 1
LEFT JOIN forecast f6 ON f6.location_id = t.location_id AND f6.valid_at = t.observed_at AND f6.lead_hours = 6
LEFT JOIN forecast f24 ON f24.location_id = t.location_id AND f24.valid_at = t.observed_at AND f24.lead_hours = 24
WHERE CAST(t.observed_at AS DATE) = DATE '{date}'
ORDER BY t.location_id, valid_at
