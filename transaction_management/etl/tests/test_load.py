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
    """Test the id-sequence rule and the schema file"""

    def test_each_node_owns_one_residue_class_above_max(self):
        for max_id in (0, 1000, 1001, 1002, 38783):
            for residue in (0, 1, 2):
                start = load.sequence_start(residue, max_id)
                self.assertGreater(start, max_id)
                self.assertLessEqual(start, max_id + 3)
                self.assertEqual(start % 3, residue)

    def test_schema_file(self):
        sql = SCHEMA.read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS stop", sql)
        self.assertIn("INCREMENT 3", sql)
        for col in config.STOP_COLUMNS:
            self.assertIn(col, sql)


if __name__ == "__main__":
    unittest.main()