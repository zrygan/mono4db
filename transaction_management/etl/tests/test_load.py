"""Unit tests for the ETL load stage."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    import psycopg2
except ImportError:
    sys.modules["psycopg2"] = MagicMock()

from etl import config, load

SCHEMA = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


class TestLoad(unittest.TestCase):
    """Test the schema file"""

    def test_schema_file(self):
        sql = SCHEMA.read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS stop", sql)
        self.assertIn("INCREMENT 3", sql)
        for col in config.STOP_COLUMNS:
            self.assertIn(col, sql)


if __name__ == "__main__":
    unittest.main()