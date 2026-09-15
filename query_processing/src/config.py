import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

QUERIES_DIR = Path("/app/queries") if Path("/app/queries").exists() else APP_DIR / "queries"
RESULTS_DIR = Path("/app/results") if Path("/app/results").exists() else APP_DIR / "results"

SQL_DIR = Path("/app/sql") if Path("/app/sql").exists() else APP_DIR / "sql"
SCHEMA_FILE = SQL_DIR / "schema.sql"
DUMP_FILE = SQL_DIR / "dump.sql"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# [fr: @zrygan; to: @all]
# Keep it as os.environ[.] instead of os.getenv(key=.)
# So that it crashes IMMEDIATELY if at least one environment variable
# is not available. This acts as an ASSERT.
DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ["DB_PORT"])
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]
