import gzip
import json
import logging
import os
import shutil
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from etl import config

log = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class RemoteFile:
    """Remote file metadata obtained before downloading.

    Attributes:
        url: Source download URL.
        size: Expected file size in bytes from Content-Length.
        etag: HTTP ETag entity tag for cache validation, if provided.
        last_modified: HTTP Last-Modified header value, if provided.
    """

    url: str
    size: int
    etag: str | None
    last_modified: str | None


def fetch_remote_metadata(url: str, timeout: int = 30) -> RemoteFile:
    """Query remote file headers to inspect size, ETag, and modification timestamp.

    Performs an HTTP HEAD request to determine file version and payload size prior
    to downloading. Enables idempotent caching, truncated transfer detection, and
    early failure if the remote resource is missing.

    Args:
        url: Source file URL to inspect.
        timeout: Network request timeout in seconds. Defaults to 30.

    Returns:
        RemoteFile: Metadata parsed from HTTP response headers.

    Raises:
        RuntimeError: If the remote server does not provide a Content-Length header.
        urllib.error.URLError: If the HTTP request fails or times out.
    """
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ddb-etl"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        size = resp.headers.get("Content-Length")
        if size is None:
            raise RuntimeError(f"{url} did not report Content-Length; cannot verify download")
        remote = RemoteFile(
            url=url,
            size=int(size),
            etag=(resp.headers.get("ETag") or "").strip('"') or None,
            last_modified=resp.headers.get("Last-Modified"),
        )
    log.info("Remote %s: %.1f MB, etag=%s", url, remote.size / 1e6, remote.etag)
    return remote


def _meta_path(dest: Path) -> Path:
    """Return the companion metadata JSON path for a target file.

    Args:
        dest: Target destination file path.

    Returns:
        Path: Path to the associated sidecar metadata file (.meta.json).
    """
    return dest.with_name(dest.name + ".meta.json")


def download(remote: RemoteFile, dest: Path, force: bool = False, timeout: int = 60) -> Path:
    """Stream a remote file to disk with atomic writing and version validation.

    Downloads the file in 1 MiB chunks to maintain constant memory usage. Writes
    to a temporary `<dest>.part` file before atomically replacing `dest` upon
    successful byte-count verification. Skips download if a matching sidecar
    metadata file (`<dest>.meta.json`) and identical file size already exist.

    Args:
        remote: Remote file metadata containing URL, size, and ETag.
        dest: Target local file path.
        force: If True, bypass cache and force re-download. Defaults to False.
        timeout: Socket read timeout in seconds. Defaults to 60.

    Returns:
        Path: Path to the verified local file (`dest`).

    Raises:
        RuntimeError: If downloaded byte count does not match `remote.size`.
        urllib.error.URLError: If the connection drops or times out.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta_path = _meta_path(dest)

    if not force and dest.exists() and meta_path.exists():
        cached = json.loads(meta_path.read_text())
        if (
            cached.get("etag") == remote.etag
            and cached.get("size") == remote.size
            and dest.stat().st_size == remote.size
        ):
            log.info("Up to date, skipping download: %s", dest)
            return dest

    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(remote.url, headers={"User-Agent": "mono4db-etl"})
    log.info("Downloading %s -> %s", remote.url, dest)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(part, "wb") as out:
        shutil.copyfileobj(resp, out, length=_CHUNK)

    got = part.stat().st_size
    if got != remote.size:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"Truncated download: got {got} bytes, expected {remote.size}")

    os.replace(part, dest)
    meta_path.write_text(
        json.dumps(
            {**asdict(remote), "downloaded_at": datetime.now(timezone.utc).isoformat()},
            indent=2,
        )
    )
    return dest


def validate_header(csv_gz: Path) -> list[str]:
    """Validate that the compressed CSV header matches expected columns in order.

    Reads only the first line of the gzip file to quickly detect schema drift
    or corrupt archives before full ingestion.

    Args:
        csv_gz: Path to the gzipped CSV file.
        expected: Ordered list of expected column names. Defaults to
            `config.SERVICES_COLUMNS` keys.

    Returns:
        list[str]: The parsed column names from the file header.

    Raises:
        ValueError: If column names, count, or ordering differ from expected.
        gzip.BadGzipFile: If the file is not a valid gzip archive.
    """
    expected = list(config.SERVICES_COLUMNS)
    with gzip.open(csv_gz, "rt", encoding="utf-8", newline="") as f:
        header = f.readline().rstrip("\r\n").split(",")

    if header != expected:
        missing = [c for c in expected if c not in header]
        extra = [c for c in header if c not in expected]
        raise ValueError(
            f"Header mismatch in {csv_gz.name}: missing={missing} extra={extra} "
            f"(order differs: {not missing and not extra})"
        )
    log.info("Header OK: %d columns", len(header))
    return header


def _sql_str(value: str | Path) -> str:
    """Escape and quote a string or path literal for DuckDB SQL.

    Args:
        value: String or Path to quote.

    Returns:
        str: Single-quoted string literal with internal single quotes doubled.
    """
    return "'" + str(value).replace("'", "''") + "'"


def _connect() -> duckdb.DuckDBPyConnection:
    """Initialize an in-memory DuckDB connection configured for streaming extract.

    Sets configured time zone, memory limits, and thread counts. Disables
    `preserve_insertion_order` to optimize streaming throughput and minimize
    memory buffering.

    Returns:
        duckdb.DuckDBPyConnection: Configured DuckDB database connection.
    """
    con = duckdb.connect()
    con.execute(f"SET TimeZone = {_sql_str(config.SOURCE_TIMEZONE)}")
    con.execute(f"SET memory_limit = {_sql_str(config.DUCKDB_MEMORY_LIMIT)}")
    con.execute(f"SET threads = {config.DUCKDB_THREADS}")
    con.execute("SET preserve_insertion_order = false")
    return con


def _check_window(date_from: str, date_to: str) -> None:
    """Validate a date window.

    Args:
        date_from: First service date of the window (YYYY-MM-DD).
        date_to: Last service date of the window (YYYY-MM-DD).

    Raises:
        ValueError: If either date is malformed or `date_from` is after `date_to`.
    """
    if date.fromisoformat(date_from) > date.fromisoformat(date_to):  # also rejects malformed dates
        raise ValueError(f"date_from {date_from} is after date_to {date_to}")


def stage_window(csv_gz: Path, dest: Path, date_from: str, date_to: str) -> Path:
    """Stage the stops of a date window into a Parquet file via DuckDB.
    
    Args:
        csv_gz: Path to the raw source `.csv.gz` file.
        dest: Destination path for the staged `.parquet` file.
        date_from: First service date of the window (YYYY-MM-DD).
        date_to: Last service date of the window (YYYY-MM-DD).

    Returns:
        Path: Path to the staged Parquet file.

    Raises:
        ValueError: If the window is invalid.
    """
    _check_window(date_from, date_to)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    columns = "{" + ", ".join(f"{_sql_str(k)}: {_sql_str(v)}" for k, v in config.SERVICES_COLUMNS.items()) + "}"

    con = _connect()
    try:
        con.execute(
            f"""
            COPY (
                SELECT "Stop:RDT-ID"              AS stop_id,
                       "Service:RDT-ID"           AS rdt_id,
                       "Service:Date"             AS service_date,
                       "Stop:Station code"        AS station_code,
                       "Stop:Station name"        AS station_name,
                       "Stop:Arrival time"        AS arrival_ts,
                       "Stop:Arrival delay"       AS arrival_delay,
                       "Stop:Arrival cancelled"   AS arrival_cancelled,
                       "Stop:Departure time"      AS departure_ts,
                       "Stop:Departure delay"     AS departure_delay,
                       "Stop:Departure cancelled" AS departure_cancelled
                FROM read_csv(
                    {_sql_str(csv_gz)},
                    header = true, auto_detect = false, delim = ',', quote = '"',
                    compression = 'gzip', columns = {columns}
                )
                WHERE "Service:Date" BETWEEN DATE {_sql_str(date_from)} AND DATE {_sql_str(date_to)}
            ) TO {_sql_str(part)} (FORMAT parquet, COMPRESSION zstd)
            """
        )
    finally:
        con.close()
    os.replace(part, dest)
    log.info("Staged %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def profile_staged(parquet: Path, date_from: str, date_to: str) -> dict:
    """Run data quality checks on the staged Parquet file and return metrics.

    Verifies essential invariants: ensures the dataset is non-empty, confirms all
    `Service:Date` values match the specified year, and validates that `Stop:RDT-ID`
    is strictly unique. Returns a lightweight summary dictionary suitable for
    Airflow XCom.

    Args:
        parquet: Path to the staged Parquet file.
        year: Expected calendar year of the dataset.

    Returns:
        dict: Summary statistics including row count, distinct entities,
            date bounds, and null timestamp counts.

    Raises:
        ValueError: If any validation checks fail (empty dataset, year mismatch,
            or duplicate stop IDs).
    """
    con = _connect()
    try:
        row = con.execute(
            f"""
            SELECT count(*)                     AS rows,
                   count(DISTINCT stop_id)      AS stop_ids,
                   count(DISTINCT rdt_id)       AS services,
                   count(DISTINCT station_code) AS stations,
                   max(stop_id)                 AS max_stop_id,
                   max(rdt_id)                  AS max_rdt_id,
                   min(service_date)::VARCHAR   AS min_date,
                   max(service_date)::VARCHAR   AS max_date,
                   count(*) FILTER (stop_id IS NULL OR rdt_id IS NULL OR station_code IS NULL) AS null_keys
            FROM read_parquet({_sql_str(parquet)})
            """
        ).fetchone()
        cols = [d[0] for d in con.description]
    finally:
        con.close()

    summary = dict(zip(cols, row))
    problems = []
    if summary["rows"] == 0:
        problems.append("no rows in the window (is the date range inside the year?)")
    else:
        if summary["stop_ids"] != summary["rows"]:
            problems.append(f"stop_id not unique ({summary['rows'] - summary['stop_ids']} duplicates)")
        if summary["null_keys"]:
            problems.append(f"{summary['null_keys']} rows with NULL stop_id/rdt_id/station_code")
        if summary["min_date"] < date_from or summary["max_date"] > date_to:
            problems.append(f"dates {summary['min_date']}..{summary['max_date']} outside {date_from}..{date_to}")
    if problems:
        raise ValueError(f"Staged file failed checks: {'; '.join(problems)}. Summary: {summary}")

    log.info("Profile: %s", summary)
    return {"staged": str(parquet), **summary}


def run_extract(year: int, date_from: str, date_to: str, force: bool = False) -> dict:
    """Execute the complete extract pipeline sequentially in a single process.

    Args:
        year: Dataset year to extract.
        date_from: First service date of the window (YYYY-MM-DD).
        date_to: Last service date of the window (YYYY-MM-DD).
        force: If True, force re-downloading even if cached locally. Defaults to False.

    Returns:
        dict: The profile of the staged window (see `profile_staged`).
    """
    _check_window(date_from, date_to)
    raw = download(fetch_remote_metadata(config.source_url(year)), config.raw_path(year), force=force)
    validate_header(raw)
    staged = stage_window(raw, config.staged_path(year, date_from, date_to), date_from, date_to)
    return profile_staged(staged, date_from, date_to)