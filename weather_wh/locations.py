"""The 52 provincial capitals the warehouse follows.

Coordinates come from the Open-Meteo geocoding API (GeoNames data, CC BY 4.0)
and are stored in weather_wh/seeds/locations.csv (inside the package, so it is installed
with it) so every run uses exactly the same points.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

SEED_FILE = Path(__file__).resolve().parent / "seeds" / "locations.csv"


@dataclass(frozen=True)
class Location:
    location_id: str
    name: str
    province: str
    latitude: float
    longitude: float


def load_locations(path: Path = SEED_FILE) -> list[Location]:
    with path.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    locations = [
        Location(r["location_id"], r["name"], r["province"], float(r["latitude"]), float(r["longitude"])) for r in rows
    ]
    ids = [location.location_id for location in locations]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate location ids in {path}")
    return locations
