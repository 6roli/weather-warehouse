-- GOLD · location_station
-- Links each provincial capital to the nearest AEMET station within 25 km, so observations
-- (stations) and forecasts (capitals) can be compared. Capitals without a nearby station are left out.
-- Params: {locations_file}, {stations_file}
WITH locations AS (
    SELECT * FROM read_csv({locations_file}, header = true)
),
stations AS (
    SELECT * FROM read_parquet({stations_file})
),
pairs AS (
    SELECT
        l.location_id, l.name AS location_name, l.province,
        l.latitude, l.longitude,
        s.station_id, s.name AS station_name, s.altitude_m AS station_altitude_m,
        haversine_km(l.latitude, l.longitude, s.latitude, s.longitude) AS distance_km
    FROM locations l
    CROSS JOIN stations s
    WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL
)
SELECT *
FROM pairs
WHERE distance_km <= 25
QUALIFY row_number() OVER (PARTITION BY location_id ORDER BY distance_km) = 1
ORDER BY location_id
