"""Dump / restore stage for the distributed `stop` ETL pipeline.

Only the CENTRAL node is snapshotted: it holds every row, and the leaves are derived from it by
`distribute`. Restoring therefore means restoring node1 and then distributing again.

pg_dump / pg_restore run inside the node1 container (`--via docker`, default), so nothing has to be
installed on the host. `--via host` uses the host's pg_dump / pg_restore instead (server-version or
newer required), which is also what you want when node1 is on another machine.
"""

import logging
import subprocess
from pathlib import Path

import psycopg2

from etl import config

log = logging.getLogger(__name__)

_OBJECTS = [f"--table={config.TABLE}", "--table=stop_id_seq", "--table=rdt_id_seq"]


def _cmd(node: str, tool: str, args: list[str], via: str) -> list[str]:
    """Build the command that runs a PostgreSQL client tool against a node.

    Args:
        node: One of config.NODES.
        tool: "pg_dump" or "pg_restore".
        args: Arguments for the tool.
        via: "docker" (run inside the node's container) or "host" (run on this machine).

    Returns:
        list[str]: The command to pass to subprocess.

    Raises:
        ValueError: If `via` is neither "docker" nor "host".
    """
    if via == "docker":
        return ["docker", "exec", "-i", config.CONTAINERS[node], tool, "-U", config.DB_USER, "-d", config.DB_NAME, *args]
    if via == "host":
        return [tool, *args, f"--dbname={config.NODE_URLS[node]}"]
    raise ValueError(f"via must be 'docker' or 'host', got {via!r}")


def dump_central(dest_dir: Path = config.DUMP_DIR, via: str = "docker") -> dict:
    """Write the central node's tables to `dest_dir/node1.dump`, replacing any previous dump atomically.

    Args:
        dest_dir: Folder for the dump. Defaults to config.DUMP_DIR.
        via: "docker" or "host" (see `_cmd`).

    Returns:
        dict: The dump path and its size in bytes.

    Raises:
        RuntimeError: If pg_dump fails.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "node1.dump"
    tmp = dest.with_name(f".{dest.name}.tmp")
    cmd = _cmd("node1", "pg_dump", ["--format=custom", "--no-owner", "--no-privileges", *_OBJECTS], via)
    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pg_dump of node1 failed: {e.stderr.decode(errors='replace').strip()}") from e
    tmp.write_bytes(result.stdout)
    tmp.replace(dest)
    size = dest.stat().st_size
    log.info("Dumped %s to %s (%.1f MB)", config.TABLE, dest, size / 1e6)
    return {"dump": str(dest), "bytes": size}


def existing_rows(db_url: str | None = None) -> int:
    """Count the rows currently in node1's `stop` table (0 if the table does not exist).

    Args:
        db_url: libpq connection URL. Defaults to config.NODE_URLS["node1"].

    Returns:
        int: Number of rows that a restore would replace.
    """
    conn = psycopg2.connect(db_url or config.NODE_URLS["node1"])
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (config.TABLE,))
            if cur.fetchone()[0] is None:
                return 0
            cur.execute(f"SELECT count(*) FROM {config.TABLE}")
            return cur.fetchone()[0]
    finally:
        conn.close()


def restore_central(src_dir: Path = config.DUMP_DIR, via: str = "docker") -> None:
    """Replace node1's `stop` table and sequences with the dump, in one transaction.

    If the restore fails, node1 is left as it was.

    Args:
        src_dir: Folder holding `node1.dump`. Defaults to config.DUMP_DIR.
        via: "docker" or "host" (see `_cmd`).

    Raises:
        FileNotFoundError: If there is no dump in `src_dir`.
        RuntimeError: If pg_restore fails.
    """
    dump = src_dir / "node1.dump"
    if not dump.is_file():
        raise FileNotFoundError(f"{dump} not found. Run `dump` first, or ask a teammate for node1.dump.")
    args = ["--clean", "--if-exists", "--no-owner", "--no-privileges", "--single-transaction", "--exit-on-error"]
    try:
        subprocess.run(_cmd("node1", "pg_restore", args, via), check=True, input=dump.read_bytes(), capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"pg_restore of node1 failed (node1 left as it was): {e.stderr.decode(errors='replace').strip()}"
        ) from e

    conn = psycopg2.connect(config.NODE_URLS["node1"])
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"ANALYZE {config.TABLE}")
    finally:
        conn.close()
    log.info("Restored node1 from %s", dump)