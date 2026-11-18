"""Unit tests for ETL configuration and path helpers."""

import unittest

from etl import config


class TestConfig(unittest.TestCase):
    """Test ETL configuration invariants and path helpers."""

    def test_nodes(self):
        self.assertEqual(config.NODES, ("node1", "node2", "node3"))
        self.assertEqual(set(config.NODE_URLS), set(config.NODES))
        self.assertEqual(set(config.CONTAINERS), set(config.NODES))

    def test_columns_match_schema(self):
        self.assertEqual(
            config.STOP_COLUMNS,
            ["stop_id", "rdt_id", "arrival_time", "departure_time", "arrival_delay", "departure_delay", "station_code"],
        )

    def test_source(self):
        self.assertEqual(config.source_url(2025), "https://blobs.duckdb.org/nl-railway/services-2025.csv.gz")
        self.assertEqual(len(config.SERVICES_COLUMNS), 20)
        self.assertEqual(config.SERVICES_COLUMNS["Stop:RDT-ID"], "BIGINT")

    def test_default_window_is_one_week(self):
        from datetime import date

        a, b = date.fromisoformat(config.DEFAULT_DATE_FROM), date.fromisoformat(config.DEFAULT_DATE_TO)
        self.assertEqual((b - a).days + 1, 7)

    def test_paths(self):
        self.assertEqual(config.raw_path(2025), config.RAW_DIR / "services-2025.csv.gz")
        self.assertEqual(
            config.staged_path(2025, "2025-01-01", "2025-01-07"),
            config.STAGING_DIR / "stop-2025-2025-01-01_2025-01-07.parquet",
        )
        self.assertEqual(
            config.clean_path(2025, "2025-01-01", "2025-01-07"),
            config.CLEAN_DIR / "stop-2025-2025-01-01_2025-01-07.parquet",
        )


if __name__ == "__main__":
    unittest.main()