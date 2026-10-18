"""Runs the SQL files in weather_wh/sql with DuckDB and writes the results as Parquet.

Each .sql file is a single SELECT (like a dbt model). Parameters are written as
{name} in the SQL and filled in here; DuckDB struct literals such as
{fetched_at: 'VARCHAR'} are left alone because they are not bare names.
"""

import re
from pathlib import Path

import duckdb

SQL_DIR = Path(__file__).resolve().parent / "sql"


def connect() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute((SQL_DIR / "_macros.sql").read_text(encoding="utf-8"))
    return connection


def sql_list(paths: list[Path]) -> str:
    """A DuckDB list literal of file paths, safely quoted."""
    if not paths:
        raise ValueError("No input files for this step")
    quoted = ["'" + path.resolve().as_posix().replace("'", "''") + "'" for path in paths]
    return "[" + ", ".join(quoted) + "]"


def render(name: str, params: dict[str, str]) -> str:
    sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    missing = set(re.findall(r"\{(\w+)\}", sql)) - set(params)
    if missing:
        raise KeyError(f"{name}.sql needs parameters: {', '.join(sorted(missing))}")
    return re.sub(r"\{(\w+)\}", lambda match: params[match.group(1)], sql)


def run_to_parquet(connection: duckdb.DuckDBPyConnection, name: str, output: Path, **params: str) -> int:
    """Executes one model and atomically replaces `output`. Returns the number of rows written."""
    sql = render(name, params)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.parquet")
    target = temporary.resolve().as_posix().replace("'", "''")
    connection.execute(f"COPY ({sql}) TO '{target}' (FORMAT parquet, COMPRESSION zstd)")
    rows = connection.execute(f"SELECT count(*) FROM read_parquet('{target}')").fetchone()[0]
    temporary.replace(output)
    return rows
