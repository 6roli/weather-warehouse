"""AEMET OpenData: hourly conventional observations from every AEMET station.

The endpoint returns the last 24 hours for all stations (about 900), so hourly
runs overlap; silver keeps one row per station and hour. Requires a free API key.
Reuse conditions: data may be used freely, citing AEMET as the source
("Fuente: AEMET"); provided as-is, without warranty.

Two-step API: the first call returns a JSON with a temporary "datos" URL; the
second call downloads the data (encoded in ISO-8859-15).
"""

from datetime import datetime

from ..bronze import BronzeRecord
from .http import SourceError, get_json

SOURCE = "aemet_observations"
ENDPOINT = "https://opendata.aemet.es/opendata/api/observacion/convencional/todas"


def fetch_observations(api_key: str, fetched_at: datetime) -> BronzeRecord:
    # The key goes in a header, so it never appears in URLs, logs or bronze files.
    index = get_json(ENDPOINT, headers={"api_key": api_key, "Accept": "application/json"}, encoding="latin-1")
    if not isinstance(index, dict) or index.get("estado") != 200 or not index.get("datos"):
        raise SourceError(f"AEMET did not return data: {index!r:.300}")
    payload = get_json(index["datos"], encoding="latin-1")
    if not isinstance(payload, list) or not payload:
        raise SourceError("AEMET returned an empty observation list")
    return BronzeRecord(source=SOURCE, fetched_at=fetched_at, request=ENDPOINT, payload=payload)
