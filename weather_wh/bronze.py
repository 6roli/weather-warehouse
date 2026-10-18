"""Bronze layer: raw API responses exactly as received, never modified.

Each fetch becomes one gzipped JSON file with a small envelope:

    bronze/source=<source>/date=YYYY-MM-DD/hour=HH.json.gz
    {"source": ..., "fetched_at": "...Z", "request": "<url without secrets>", "context": {...}, "payload": <raw>}

Keeping the raw payload means silver and gold can always be rebuilt with new logic.
"""

import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class BronzeRecord:
    source: str
    fetched_at: datetime  # UTC
    request: str
    payload: object
    context: dict | None = None


def bronze_path(data_dir: Path, source: str, fetched_at: datetime) -> Path:
    stamp = fetched_at.astimezone(timezone.utc)
    return data_dir / "bronze" / f"source={source}" / f"date={stamp:%Y-%m-%d}" / f"hour={stamp:%H}.json.gz"


def write_bronze(data_dir: Path, record: BronzeRecord) -> Path:
    path = bronze_path(data_dir, record.source, record.fetched_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "source": record.source,
        "fetched_at": record.fetched_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": record.request,
        "context": record.context or {},
        "payload": record.payload,
    }
    # Write to a temporary file first so a crash never leaves a half-written bronze file.
    temporary = path.with_suffix(".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as file:
        json.dump(envelope, file, ensure_ascii=False)
    temporary.replace(path)
    return path
