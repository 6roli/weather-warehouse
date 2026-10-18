-- Helpers shared by every layer. Loaded once per DuckDB connection.

-- Parses the timestamps the sources use ("2026-10-18T14:00", "...:00Z", "...+0000") as UTC TIMESTAMP.
CREATE OR REPLACE MACRO utc_ts(x) AS
    CAST(regexp_replace(replace(CAST(x AS VARCHAR), 'T', ' '), '(Z|[+-]00:?00)$', '') AS TIMESTAMP);

-- Great-circle distance in km between two latitude/longitude points.
CREATE OR REPLACE MACRO haversine_km(lat1, lon1, lat2, lon2) AS
    2 * 6371 * asin(sqrt(
        pow(sin(radians(lat2 - lat1) / 2), 2)
        + cos(radians(lat1)) * cos(radians(lat2)) * pow(sin(radians(lon2 - lon1) / 2), 2)
    ));
