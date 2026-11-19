"""Configuration settings and path helpers for the Dutch Railway ETL pipeline."""

import os
from pathlib import Path
from urllib.parse import quote

ETL_DIR = Path(__file__).resolve().parents[1]
TM_DIR = ETL_DIR.parent

SOURCE_URL_TEMPLATE = "https://blobs.duckdb.org/nl-railway/services-{year}.csv.gz"
SOURCE_TIMEZONE = "Europe/Amsterdam"
DEFAULT_YEAR = 2025
DEFAULT_DATE_FROM = "2025-11-01"
DEFAULT_DATE_TO = "2025-11-01"

SERVICES_COLUMNS: dict[str, str] = {
    "Service:RDT-ID": "BIGINT",
    "Service:Date": "DATE",
    "Service:Type": "VARCHAR",
    "Service:Company": "VARCHAR",
    "Service:Train number": "BIGINT",
    "Service:Completely cancelled": "BOOLEAN",
    "Service:Partly cancelled": "BOOLEAN",
    "Service:Maximum delay": "BIGINT",
    "Stop:RDT-ID": "BIGINT",
    "Stop:Station code": "VARCHAR",
    "Stop:Station name": "VARCHAR",
    "Stop:Arrival time": "TIMESTAMPTZ",
    "Stop:Arrival delay": "BIGINT",
    "Stop:Arrival cancelled": "BOOLEAN",
    "Stop:Departure time": "TIMESTAMPTZ",
    "Stop:Departure delay": "BIGINT",
    "Stop:Departure cancelled": "BOOLEAN",
    "Stop:Platform change": "BOOLEAN",
    "Stop:Planned platform": "VARCHAR",
    "Stop:Actual platform": "VARCHAR",
}

STATION_CODE_MERGES: dict[str, str] = {"BERHBT": "BERHBL"}
STATION_CODE_RENAMES: dict[tuple[str, str], str] = {("LAND", "Venezia Santa Lucia"): "VENEZ"}

DATA_DIR = Path(os.environ.get("DDB_ETL_DATA_DIR", ETL_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
CLEAN_DIR = DATA_DIR / "clean"
DUMP_DIR = DATA_DIR / "dumps"

SCHEMA_SQL = Path(os.environ.get("DDB_SCHEMA_SQL", TM_DIR / "db" / "schema.sql"))

DUCKDB_MEMORY_LIMIT = os.environ.get("DDB_ETL_DUCKDB_MEMORY_LIMIT", "2GB")
DUCKDB_THREADS = int(os.environ.get("DDB_ETL_DUCKDB_THREADS", "4"))

TABLE = "stop"
STOP_COLUMNS = ["stop_id", "rdt_id", "arrival_time", "departure_time", "arrival_delay", "departure_delay", "station_code"]

DB_USER = "app"
DB_NAME = "appdb"
CENTRAL_PORT = 5441
CENTRAL_CONTAINER = "db-central-node"

def _central_url() -> str:
    """Build the URL of the central node, honouring a DDB_CENTRAL_URL override.

    Returns:
        str: The override from the environment if set, else a localhost URL built from DB_PASSWORD.
    """
    password = quote(os.environ.get("DB_PASSWORD", ""), safe="")
    default = f"postgresql://{DB_USER}:{password}@localhost:{CENTRAL_PORT}/{DB_NAME}"
    return os.environ.get("DDB_CENTRAL_URL", default)  # override to point at a remote machine


CENTRAL_URL = _central_url()

def source_url(year: int) -> str:
    """Format remote download URL for a given dataset year.

    Args:
        year: Calendar year of the NS services dataset.

    Returns:
        str: Fully-qualified HTTP download URL.
    """
    return SOURCE_URL_TEMPLATE.format(year=year)


def raw_path(year: int) -> Path:
    """Return local filesystem path for the raw compressed services archive.

    Args:
        year: Calendar year of the NS services dataset.

    Returns:
        Path: Path to the destination `.csv.gz` file.
    """
    return RAW_DIR / f"services-{year}.csv.gz"


def staged_path(year: int, date_from: str, date_to: str) -> Path:
    """Return local filesystem path for the staged typed Parquet file.

    Args:
        year: Calendar year of the NS services dataset.

    Returns:
        Path: Path to the destination staged `.parquet` file.
    """
    return STAGING_DIR / f"stop-{year}-{date_from}_{date_to}.parquet"


def clean_path(year: int, date_from: str, date_to: str) -> Path:
    """Return the cleaned Parquet (what gets loaded into the central node) of a date window.

    Args:
        year: Calendar year of the NS services dataset.
        date_from: First service date of the window (YYYY-MM-DD).
        date_to: Last service date of the window (YYYY-MM-DD).

    Returns:
        Path: Path to the cleaned `.parquet` file.
    """
    return CLEAN_DIR / f"stop-{year}-{date_from}_{date_to}.parquet"