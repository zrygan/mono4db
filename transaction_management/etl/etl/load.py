"""Load stage for the distributed `stop` ETL pipeline.

Loads the cleaned rows into the CENTRAL node (node1) only, with a streaming COPY inside one atomic
transaction. The leaf nodes are filled afterwards by the central node itself (central/distribute.sql).
"""

import logging
import tempfile
from pathlib import Path

import psycopg2

from etl import config
from etl.extract import _connect, _sql_str

log = logging.getLogger(__name__)


def _to_csv(parquet: Path, csv: Path) -> None:
    """Export Parquet table data to headerless CSV format for PostgreSQL COPY.

    Args:
        parquet: Source Parquet file path.
        csv: Destination CSV file path.
    """
    con = _connect()
    try:
        con.execute(f"COPY (FROM read_parquet({_sql_str(parquet)})) TO {_sql_str(csv)} (FORMAT csv, HEADER false)")
    finally:
        con.close()


def load_central(clean: Path, max_stop_id: int, max_rdt_id: int, db_url: str | None = None) -> dict:
    """Replace the central node's `stop` table with the cleaned rows and reset its id sequences.

    Re-running reloads the same state (and discards any edits made through the app). Doesnt touch leaf nodes

    Args:
        clean: Cleaned Parquet from the transform.
        max_stop_id: Highest stop_id in the data (seeds `stop_id_seq`).
        max_rdt_id: Highest rdt_id in the data (seeds `rdt_id_seq`).
        db_url: libpq connection URL. Defaults to config.CENTRAL_URL.

    Returns:
        dict: The row count of node1 after the load.
    """
    db_url = db_url or config.CENTRAL_URL
    with tempfile.TemporaryDirectory(dir=clean.parent, prefix=".load-") as tmp:
        csv = Path(tmp) / "stop.csv"
        _to_csv(clean, csv)

        conn = psycopg2.connect(db_url)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(config.SCHEMA_SQL.read_text())
                cur.execute(f"TRUNCATE {config.TABLE}")
                with open(csv, encoding="utf-8") as f:
                    cur.copy_expert(
                        f"COPY {config.TABLE} ({', '.join(config.STOP_COLUMNS)}) FROM STDIN WITH (FORMAT csv)", f
                    )
                reset_sequences(cur, max_stop_id, max_rdt_id)
                cur.execute(f"SELECT count(*) FROM {config.TABLE}")
                rows = cur.fetchone()[0]
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"ANALYZE {config.TABLE}")
        finally:
            conn.close()

    log.info("node1 (central) now holds %d rows", rows)
    return {"node1": rows}