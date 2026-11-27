"""Dump stage for the Dutch Railway ETL pipeline.

Snapshots the central node in PostgreSQL (dutch_railway_db) into a pg_dump
custom-format archive, so others can restore the database with
scripts/setup_db.py instead of re-running the whole pipeline.
"""

import logging
import subprocess
from pathlib import Path

from etl import config

log = logging.getLogger(__name__)

_OBJECTS = [f"--table={config.TABLE}", "--table=stop_id_seq", "--table=rdt_id_seq"]


def _cmd(tool: str, args: list[str], via: str) -> list[str]:
    """Build the command that runs a PostgreSQL client tool against the central node.

    Args:
        tool: "pg_dump" or "pg_restore".
        args: Arguments for the tool.
        via: "docker" (run inside the node1 container) or "host" (run on this machine).

    Returns:
        list[str]: The command to pass to subprocess.

    Raises:
        ValueError: If `via` is neither "docker" nor "host".
    """
    if via == "docker":
        return ["docker", "exec", "-i", config.CENTRAL_CONTAINER, tool, "-U", config.DB_USER, "-d", config.DB_NAME, *args]
    if via == "host":
        return [tool, *args, f"--dbname={config.CENTRAL_URL}"]
    raise ValueError(f"via must be 'docker' or 'host', got {via!r}")


def dump_central(dest_dir: Path = config.DUMP_DIR, via: str = "docker") -> dict:
    """Write the central node table to `dump`, replacing any previous dump atomically.

    Args:
        dump: Destination `.dump` file (pg_dump custom format).
        db_url: libpq connection URL. Defaults to config.DB_URL.

    Returns:
        dict: The dump path and its size in bytes.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "central.dump"
    tmp = dest.with_name(f".{dest.name}.tmp")
    cmd = _cmd("pg_dump", ["--format=custom", "--no-owner", "--no-privileges", *_OBJECTS], via)
    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pg_dump of node1 failed: {e.stderr.decode(errors='replace').strip()}") from e
    tmp.write_bytes(result.stdout)
    tmp.replace(dest)
    size = dest.stat().st_size
    log.info("Dumped %s to %s (%.1f MB)", config.TABLE, dest, size / 1e6)
    return {"dump": str(dest), "bytes": size}