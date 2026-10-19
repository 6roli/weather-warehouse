"""Optional copy of the lake in a public Hugging Face Storage Bucket.

The GitHub Actions runner starts empty every hour, so each run downloads only the
partitions it needs (a few days), rebuilds them and uploads the changed files.
Anyone can then read the data over HTTPS, e.g. in DuckDB:

    SELECT * FROM 'https://huggingface.co/buckets/groli/weather-warehouse/resolve/gold/latest_forecast/data.parquet';
"""

import logging
from pathlib import Path

from huggingface_hub import batch_bucket_files, sync_bucket

from .lake import Lake

log = logging.getLogger(__name__)


class Remote:
    def __init__(self, bucket: str, token: str):
        self.bucket = bucket
        self.token = token

    def pull(self, lake: Lake, prefixes: list[str]) -> None:
        """Downloads the given folders (e.g. 'bronze/source=x/date=2026-10-18') if they exist remotely."""
        for prefix in prefixes:
            try:
                sync_bucket(f"hf://buckets/{self.bucket}/{prefix}", str(lake.root / prefix), token=self.token, quiet=True)
            except Exception as error:  # noqa: BLE001 — a missing folder simply means no data yet
                log.info("Nothing to pull for %s (%s)", prefix, type(error).__name__)

    def status_markdown(self) -> str:
        """Files, size and date range per table, read from the bucket listing (no downloads)."""
        from collections import defaultdict
        from datetime import datetime, timezone

        from huggingface_hub import list_bucket_tree

        tables: dict[tuple[str, str], dict] = defaultdict(lambda: {"files": 0, "bytes": 0, "dates": set()})
        for entry in list_bucket_tree(self.bucket, recursive=True, token=self.token):
            path = getattr(entry, "path", "")
            parts = path.split("/")
            if len(parts) < 3 or parts[0] not in {"bronze", "silver", "gold"} or not path.endswith((".gz", ".parquet")):
                continue
            table = tables[(parts[0], parts[1])]
            table["files"] += 1
            table["bytes"] += getattr(entry, "size", 0) or 0
            table["dates"].update(p.split("=", 1)[1] for p in parts[2:] if "date=" in p)
        lines = [
            "# Data warehouse status",
            "",
            f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from `hf://buckets/{self.bucket}`.",
            "",
            "| Layer | Table | Files | Size (MB) | First day | Last day |",
            "|---|---|---|---|---|---|",
        ]
        for (layer, name), info in sorted(tables.items()):
            dates = sorted(info["dates"])
            first, last = (dates[0], dates[-1]) if dates else ("-", "-")
            lines.append(f"| {layer} | {name} | {info['files']} | {info['bytes'] / 1e6:.1f} | {first} | {last} |")
        return "\n".join(lines) + "\n"

    def push(self, lake: Lake, paths: list[Path]) -> None:
        if not paths:
            return
        # Several files per call keeps the number of API operations low.
        for start in range(0, len(paths), 50):
            batch = paths[start : start + 50]
            batch_bucket_files(self.bucket, add=[(str(path), lake.relative(path)) for path in batch], token=self.token)
        log.info("Uploaded %d files to %s", len(paths), self.bucket)
