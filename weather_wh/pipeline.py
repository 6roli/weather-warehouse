"""Command line entry point.

    weather-wh hourly            fetch sources → bronze, rebuild silver and gold for today and yesterday
    weather-wh rebuild --days 3  rebuild silver and gold from bronze for the last N days (no fetching)
    weather-wh status [--remote] print a short report of what the lake (or the bucket) contains, as Markdown

Exit code is non-zero only if every source failed, so one flaky API does not stop the others.
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from .bronze import write_bronze
from .config import Settings, load_settings
from .lake import Lake
from .layers import build_gold, build_silver
from .locations import load_locations
from .remote import Remote
from .sources import aemet, open_meteo
from .transform import connect
from .web import build_web_snapshot

log = logging.getLogger("weather_wh")


def _remote(settings: Settings) -> Remote | None:
    return Remote(settings.hf_bucket, settings.hf_token) if settings.publishes else None


def _pull_inputs(remote: Remote | None, lake: Lake, days: list[date]) -> None:
    """Brings the partitions needed to rebuild `days` from the bucket (no-op when local only)."""
    if remote is None:
        return
    first, last = min(days), max(days)
    prefixes = []
    for offset in range((last - first).days + 2):  # include the day after for 24 h observation windows
        day = first + timedelta(days=offset)
        prefixes += [lake.relative(lake.bronze_dir(source, day)) for source in (open_meteo.SOURCE, aemet.SOURCE)]
    for offset in range(4):  # forecasts issued up to 3 days before the oldest day
        prefixes.append(lake.relative(lake.silver_forecasts(first - timedelta(days=offset)).parent))
    prefixes.append(lake.relative(lake.silver_observations(first - timedelta(days=1)).parent))
    remote.pull(lake, prefixes)


def fetch(settings: Settings, lake: Lake, now: datetime) -> tuple[list, list[str]]:
    """Downloads every configured source into bronze. Returns (written files, failed sources)."""
    written, failed = [], []
    try:
        written.append(write_bronze(lake.root, open_meteo.fetch_forecast(load_locations(), now)))
    except Exception as error:  # noqa: BLE001
        log.error("Open-Meteo failed: %s", error)
        failed.append(open_meteo.SOURCE)
    if settings.aemet_api_key:
        try:
            written.append(write_bronze(lake.root, aemet.fetch_observations(settings.aemet_api_key, now)))
        except Exception as error:  # noqa: BLE001
            log.error("AEMET failed: %s", error)
            failed.append(aemet.SOURCE)
    else:
        log.info("AEMET_API_KEY not set: skipping observations")
    for path in written:
        log.info("bronze: %s", lake.relative(path))
    return written, failed


def rebuild(lake: Lake, days: list[date], today: date) -> list:
    connection = connect()
    return build_silver(connection, lake, days) + build_gold(connection, lake, days, today)


def run_hourly(settings: Settings, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    lake, remote = Lake(settings.data_dir), _remote(settings)
    today = now.date()
    days = [today - timedelta(days=1), today]

    _pull_inputs(remote, lake, days)
    bronze, failed = fetch(settings, lake, now)
    if remote:
        remote.push(lake, bronze)  # raw data first: it is the part that cannot be recreated
    # Upload each layer as soon as it is built, so a failure in gold never loses silver.
    connection = connect()
    silver = build_silver(connection, lake, days)
    if remote:
        remote.push(lake, silver)
    gold = build_gold(connection, lake, days, today)
    snapshot = build_web_snapshot(connection, lake, now)
    if remote:
        remote.push(lake, gold + ([snapshot] if snapshot else []))

    sources = 1 + bool(settings.aemet_api_key)
    if len(failed) == sources:
        log.error("Every source failed")
        return 1
    return 0


def run_rebuild(settings: Settings, days_back: int) -> int:
    lake, remote = Lake(settings.data_dir), _remote(settings)
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=offset) for offset in range(days_back - 1, -1, -1)]
    _pull_inputs(remote, lake, days)
    outputs = rebuild(lake, days, today)
    snapshot = build_web_snapshot(connect(), lake, datetime.now(timezone.utc))
    outputs += [snapshot] if snapshot else []
    if remote:
        remote.push(lake, outputs)
    return 0


def status_report(lake: Lake) -> str:
    """Markdown summary of the local lake: files and rows per table."""
    connection = connect()
    lines = ["# Data warehouse status", "", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.", ""]
    lines += ["| Layer | Table | Files | Rows | First | Last |", "|---|---|---|---|---|---|"]
    for layer in ("bronze", "silver", "gold"):
        base = lake.root / layer
        if not base.exists():
            continue
        for table in sorted(p for p in base.iterdir() if p.is_dir()):
            files = sorted(table.rglob("*.json.gz" if layer == "bronze" else "*.parquet"))
            partitions = sorted({part.split("=", 1)[1] for f in files for part in f.parent.parts if "date=" in part})
            rows = "-"
            if layer != "bronze" and files:
                paths = ", ".join("'" + f.resolve().as_posix() + "'" for f in files)
                rows = f"{connection.execute(f'SELECT count(*) FROM read_parquet([{paths}])').fetchone()[0]:,}"
            first, last = (partitions[0], partitions[-1]) if partitions else ("-", "-")
            lines.append(f"| {layer} | {table.name} | {len(files)} | {rows} | {first} | {last} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="weather-wh", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hourly", help="fetch sources and rebuild today and yesterday")
    rebuild_parser = commands.add_parser("rebuild", help="rebuild silver and gold from bronze")
    rebuild_parser.add_argument("--days", type=int, default=2, help="how many days back to rebuild (default 2)")
    status_parser = commands.add_parser("status", help="print a Markdown report of the lake")
    status_parser.add_argument("--remote", action="store_true", help="report on the Hugging Face bucket instead of local files")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.command == "hourly":
        return run_hourly(settings)
    if args.command == "rebuild":
        if args.days < 1:
            parser.error("--days must be at least 1")
        return run_rebuild(settings, args.days)
    if args.remote:
        remote = _remote(settings)
        if remote is None:
            parser.error("--remote needs HF_BUCKET and HF_TOKEN")
        print(remote.status_markdown())
    else:
        print(status_report(Lake(settings.data_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
