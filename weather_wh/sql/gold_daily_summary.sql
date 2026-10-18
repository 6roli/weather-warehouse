-- GOLD · daily_summary
-- Per capital and day: what was observed, and how accurate the forecasts were by lead time
-- (mean absolute temperature error). A small table meant for dashboards.
-- Params: {date}, {forecast_vs_observed_file}
WITH fvo AS (
    SELECT * FROM read_parquet({forecast_vs_observed_file})
),
observed AS (
    -- fvo repeats each observation once per lead time; keep one row per hour
    SELECT DISTINCT location_id, valid_at, observed_temperature_c, observed_precipitation_mm, observed_wind_speed_kmh
    FROM fvo
),
skill AS (
    SELECT
        location_id,
        round(avg(abs(error_temperature_c)) FILTER (WHERE lead_hours BETWEEN 1 AND 6), 2) AS temperature_mae_lead_1_6h,
        round(avg(abs(error_temperature_c)) FILTER (WHERE lead_hours BETWEEN 7 AND 24), 2) AS temperature_mae_lead_7_24h,
        round(avg(abs(error_temperature_c)) FILTER (WHERE lead_hours BETWEEN 25 AND 48), 2) AS temperature_mae_lead_25_48h,
        round(avg(abs(error_temperature_c)) FILTER (WHERE lead_hours BETWEEN 49 AND 72), 2) AS temperature_mae_lead_49_72h
    FROM fvo
    GROUP BY location_id
)
SELECT
    o.location_id,
    DATE '{date}' AS date,
    count(*) AS observed_hours,
    min(o.observed_temperature_c) AS temperature_min_c,
    max(o.observed_temperature_c) AS temperature_max_c,
    round(avg(o.observed_temperature_c), 2) AS temperature_mean_c,
    sum(o.observed_precipitation_mm) AS precipitation_sum_mm,
    max(o.observed_wind_speed_kmh) AS wind_speed_max_kmh,
    any_value(s.temperature_mae_lead_1_6h) AS temperature_mae_lead_1_6h,
    any_value(s.temperature_mae_lead_7_24h) AS temperature_mae_lead_7_24h,
    any_value(s.temperature_mae_lead_25_48h) AS temperature_mae_lead_25_48h,
    any_value(s.temperature_mae_lead_49_72h) AS temperature_mae_lead_49_72h
FROM observed o
JOIN skill s USING (location_id)
GROUP BY o.location_id
ORDER BY o.location_id
