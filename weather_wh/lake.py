"""Where every table lives inside the data lake (same layout locally and in the bucket).

    bronze/source=<source>/date=YYYY-MM-DD/hour=HH.json.gz
    silver/forecasts_hourly/issue_date=YYYY-MM-DD/data.parquet
    silver/observations_hourly/date=YYYY-MM-DD/data.parquet
    silver/stations/data.parquet
    gold/location_station/data.parquet
    gold/forecast_vs_observed/date=YYYY-MM-DD/data.parquet
    gold/training_features/date=YYYY-MM-DD/data.parquet
    gold/daily_summary/date=YYYY-MM-DD/data.parquet
    gold/latest_forecast/data.parquet
    gold/web/snapshot.json                     small JSON for websites (see web.py)

Partitioning by day keeps every hourly run small: it only rewrites today's and
yesterday's files, and readers can select the days they need.
"""

from datetime import date
from pathlib import Path


class Lake:
    def __init__(self, root: Path):
        self.root = root

    # bronze
    def bronze_dir(self, source: str, day: date) -> Path:
        return self.root / "bronze" / f"source={source}" / f"date={day.isoformat()}"

    def bronze_files(self, source: str, days: list[date]) -> list[Path]:
        return sorted(path for day in days for path in self.bronze_dir(source, day).glob("hour=*.json.gz"))

    # silver
    def silver_forecasts(self, issue_day: date) -> Path:
        return self.root / "silver" / "forecasts_hourly" / f"issue_date={issue_day.isoformat()}" / "data.parquet"

    def silver_observations(self, day: date) -> Path:
        return self.root / "silver" / "observations_hourly" / f"date={day.isoformat()}" / "data.parquet"

    def silver_stations(self) -> Path:
        return self.root / "silver" / "stations" / "data.parquet"

    # gold
    def gold_location_station(self) -> Path:
        return self.root / "gold" / "location_station" / "data.parquet"

    def gold_partition(self, table: str, day: date) -> Path:
        return self.root / "gold" / table / f"date={day.isoformat()}" / "data.parquet"

    def gold_latest_forecast(self) -> Path:
        return self.root / "gold" / "latest_forecast" / "data.parquet"

    def gold_web_snapshot(self) -> Path:
        return self.root / "gold" / "web" / "snapshot.json"

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


def existing(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]
