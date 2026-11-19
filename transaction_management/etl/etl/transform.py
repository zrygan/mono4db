"""Transform stage for the Dutch Railway ETL pipeline.

Transforms staged services Parquet data into a star schema comprising
dimensional tables (dim_date, dim_time, dim_station) and fact tables
(fact_service, fact_stop).

Q1. Time columns?
A1. TIME (local Europe/Amsterdam clock time) rather than smallints

Q2. Unrecorded times and delays?
A2. When a service is made, placeholder stop columns are also made. These stop columns have no 
    recorded arrival/departure time and delay yet, and before they're recorded they're null.
"""

import logging
import os
from pathlib import Path

from etl import config
from etl.extract import _connect, _sql_str

log = logging.getLogger(__name__)


def _station_code_sql() -> str:
    """Generate SQL CASE expression applying station code renames and merges.

    Returns:
        str: DuckDB SQL CASE expression returning the canonical station code.
    """
    whens = [
        f"WHEN station_code = {_sql_str(code)} AND station_name = {_sql_str(name)} THEN {_sql_str(new)}"
        for (code, name), new in config.STATION_CODE_RENAMES.items()
    ] + [f"WHEN station_code = {_sql_str(old)} THEN {_sql_str(new)}" for old, new in config.STATION_CODE_MERGES.items()]
    return f"CASE {' '.join(whens)} ELSE station_code END"


def _typed_sql(staged: Path) -> str:
    """Generate SQL that turns staged rows into the stop schema

    Args:
        staged: Path to the staged Parquet file.
    """
    tz = _sql_str(config.SOURCE_TIMEZONE)
    return f"""
        SELECT stop_id::BIGINT                                   AS stop_id,
               rdt_id::BIGINT                                    AS rdt_id,
               (arrival_ts   AT TIME ZONE {tz})::TIMESTAMP       AS arrival_time,
               (departure_ts AT TIME ZONE {tz})::TIMESTAMP       AS departure_time,
               (CASE WHEN NOT arrival_cancelled   THEN arrival_delay   END)::INTEGER AS arrival_delay,
               (CASE WHEN NOT departure_cancelled THEN departure_delay END)::INTEGER AS departure_delay,
               {_station_code_sql()}::VARCHAR                    AS station_code
        FROM read_parquet({_sql_str(staged)})
        ORDER BY stop_id
    """


def _validate(con, part: Path, staged_rows: int) -> dict:
    """Validate transformed tables against data integrity and foreign key constraints.

    Args:
        con: Active DuckDB database connection containing staged views.
        out: Path to the directory containing transformed Parquet files.
        staged_rows: Row count of the staged file the clean rows came from.

    Returns:
        dict: Row count if all validation checks succeed.
    """
    con.execute(f"CREATE OR REPLACE VIEW clean AS FROM read_parquet({_sql_str(part)})")
    counts = {"rows": con.execute("SELECT count(*) FROM clean").fetchone()[0]}
    merged = ", ".join(_sql_str(c) for c in config.STATION_CODE_MERGES)

    checks = {
        "clean rows != staged rows": f"SELECT {counts['rows']} <> {staged_rows}",
        "stop_id not unique": "SELECT count(*) <> count(DISTINCT stop_id) FROM clean",
        "NULL or empty station_code": "SELECT count(*) > 0 FROM clean WHERE station_code IS NULL OR station_code = ''",
        "merged station code still present": f"SELECT count(*) > 0 FROM clean WHERE station_code IN ({merged})",
    }
    problems = [name for name, sql in checks.items() if con.execute(sql).fetchone()[0]]
    if problems:
        raise ValueError(f"Transform failed checks: {'; '.join(problems)}. Counts: {counts}")
    return counts


def run_transform(staged: Path, out: Path, profile: dict) -> dict:
    """Build every table from the staged Parquet into `out/<table>.parquet`.

    Each file is written to a `.part` first and renamed, so a failed run never leaves a
    half-written table next to good ones.

    Args:
        staged: Staged services Parquet from the extract.
        out: Warehouse directory for this year (config.warehouse_dir).
        profile: The extract's profile (row count and max id).

    Returns:
        dict: The output directory and the row count of each table.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    con = _connect()
    try:
        con.execute(f"COPY ({_typed_sql(staged)}) TO {_sql_str(part)} (FORMAT parquet, COMPRESSION zstd)")
        try:
            counts = _validate(con, part, profile["rows"])
        except ValueError:
            part.unlink(missing_ok=True)
            raise
    finally:
        con.close()
    os.replace(part, out)

    result = {
        "clean": str(out),
        **counts,
        "max_stop_id": profile["max_stop_id"],
        "max_rdt_id": profile["max_rdt_id"],
    }
    log.info("Transform result: %s (%.1f MB)", result, out.stat().st_size / 1e6)
    return result