"""Unit tests for the ETL extract stage."""

import gzip
import tempfile
import unittest
from pathlib import Path

from etl import config, extract


def _row(**kw) -> list[str]:
    base = {
        "Service:RDT-ID": "1", "Service:Date": "2025-01-02", "Service:Type": "Intercity", "Service:Company": "NS",
        "Service:Train number": "100", "Service:Completely cancelled": "false", "Service:Partly cancelled": "false",
        "Service:Maximum delay": "0", "Stop:RDT-ID": "10", "Stop:Station code": "UT", "Stop:Station name": "Utrecht",
        "Stop:Arrival time": "2025-01-02 09:05:00+01", "Stop:Arrival delay": "60", "Stop:Arrival cancelled": "false",
        "Stop:Departure time": "2025-01-02 09:07:00+01", "Stop:Departure delay": "0",
        "Stop:Departure cancelled": "false", "Stop:Platform change": "false", "Stop:Planned platform": "5",
        "Stop:Actual platform": "5",
    }
    base.update(kw)
    return [base[c] for c in config.SERVICES_COLUMNS]


def _write(path: Path, rows: list[list[str]], header: list[str] | None = None) -> Path:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        f.write(",".join(header or list(config.SERVICES_COLUMNS)) + "\n")
        for r in rows:
            f.write(",".join(r) + "\n")
    return path


class TestExtract(unittest.TestCase):
    """Test extract helper functions and validation logic."""

    def test_header_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = _write(Path(tmp) / "x.csv.gz", [], header=list(config.SERVICES_COLUMNS)[:-1])
            with self.assertRaises(ValueError):
                extract.validate_header(bad)

    def test_window_keeps_whole_services_only(self):
        rows = [
            _row(**{"Stop:RDT-ID": "10", "Service:RDT-ID": "1", "Service:Date": "2025-01-02"}),
            _row(**{"Stop:RDT-ID": "11", "Service:RDT-ID": "1", "Service:Date": "2025-01-02"}),
            _row(**{"Stop:RDT-ID": "20", "Service:RDT-ID": "2", "Service:Date": "2025-01-09"}),  # outside
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw = _write(tmp / "x.csv.gz", rows)
            staged = extract.stage_window(raw, tmp / "s.parquet", "2025-01-01", "2025-01-07")
            profile = extract.profile_staged(staged, "2025-01-01", "2025-01-07")
            self.assertEqual((profile["rows"], profile["services"], profile["max_stop_id"]), (2, 1, 11))

    def test_empty_window_fails_the_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw = _write(tmp / "x.csv.gz", [_row()])
            staged = extract.stage_window(raw, tmp / "s.parquet", "2025-03-01", "2025-03-07")
            with self.assertRaises(ValueError):
                extract.profile_staged(staged, "2025-03-01", "2025-03-07")

    def test_duplicate_stop_ids_fail_the_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            raw = _write(tmp / "x.csv.gz", [_row(), _row()])
            staged = extract.stage_window(raw, tmp / "s.parquet", "2025-01-01", "2025-01-07")
            with self.assertRaises(ValueError):
                extract.profile_staged(staged, "2025-01-01", "2025-01-07")

    def test_reversed_window(self):
        with self.assertRaises(ValueError):
            extract._check_window("2025-01-07", "2025-01-01")


if __name__ == "__main__":
    unittest.main()