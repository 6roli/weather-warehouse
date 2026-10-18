-- SILVER · stations
-- AEMET station metadata as seen in the most recent observation download.
-- Params: {bronze_files}
WITH raw AS (
    SELECT utc_ts(fetched_at) AS fetched_at, unnest(CAST(payload AS JSON[])) AS o
    FROM read_json({bronze_files}, columns = {fetched_at: 'VARCHAR', payload: 'JSON'},
                   maximum_object_size = 134217728)
)
SELECT
    o ->> 'idema' AS station_id,
    o ->> 'ubi' AS name,
    TRY_CAST(o ->> 'lat' AS DOUBLE) AS latitude,
    TRY_CAST(o ->> 'lon' AS DOUBLE) AS longitude,
    TRY_CAST(o ->> 'alt' AS DOUBLE) AS altitude_m,
    fetched_at AS last_seen_at
FROM raw
WHERE o ->> 'idema' IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY station_id ORDER BY fetched_at DESC) = 1
ORDER BY station_id
