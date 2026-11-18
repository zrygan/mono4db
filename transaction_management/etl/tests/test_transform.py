"""Unit tests for the ETL transform stage."""

import tempfile
import unittest
from pathlib import Path

import duckdb

from etl import transform

_COLS = ("stop_id BIGINT, rdt_id BIGINT, service_date DATE, station_code VARCHAR, station_name VARCHAR, "
         "arrival_ts TIMESTAMPTZ, arrival_delay BIGINT, arrival_cancelled BOOLEAN, "
         "departure_ts TIMESTAMPTZ, departure_delay BIGINT, departure_cancelled BOOLEAN")


def _stage(path: Path, rows: list[tuple]) -> dict:
    con = duckdb.connect()
    con.execute("SET TimeZone='Europe/Amsterdam'")
    con.execute(f"CREATE TABLE s({_COLS})")
    con.executemany("INSERT INTO s VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute(f"COPY s TO '{path}' (FORMAT parquet)")
    return {"rows": len(rows), "max_stop_id": max(r[0] for r in rows), "max_rdt_id": max(r[1] for r in rows)}


def _r(i, station, name="x", arr="2025-01-02 09:05:00+01", dep="2025-01-02 09:07:00+01",
       ad=60, ac=False, dd=0, dc=False):
    return (i, 1 + i // 3, "2025-01-02", station, name, arr, ad, ac, dep, dd, dc)


class TestTransform(unittest.TestCase):
    """Test SQL query generation and transformation helper functions."""

    def _run(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = Path(tmp.name)
        profile = _stage(tmp / "s.parquet", rows)
        result = transform.run_transform(tmp / "s.parquet", tmp / "out" / "clean.parquet", profile)
        return Path(result["clean"]), result

    def test_keeps_every_row_and_reports_id_maxima(self):
        clean, result = self._run([_r(i, "AA") for i in range(1, 8)])
        self.assertEqual(result["rows"], 7)
        self.assertEqual((result["max_stop_id"], result["max_rdt_id"]), (7, 3))
        self.assertEqual(duckdb.sql(f"SELECT count(*) FROM '{clean}'").fetchone()[0], 7)

    def test_times_are_amsterdam_clock_time_and_delays_follow_cancellation(self):
        rows = [
            _r(1, "AA", arr="2025-01-02 09:05:00+01", ad=60),
            _r(2, "ZZ", arr="2025-07-02 09:05:00+02", ad=120, ac=True, dd=30, dc=False),  # summer, cancelled arrival
        ]
        clean, _ = self._run(rows)
        got = duckdb.sql(
            f"SELECT stop_id, arrival_time::VARCHAR, arrival_delay, departure_delay FROM '{clean}' ORDER BY stop_id"
        ).fetchall()
        self.assertEqual(got, [(1, "09:05:00", 60, 0), (2, "09:05:00", None, 30)])

    def test_station_merge_and_rename(self):
        rows = [_r(1, "BERHBT"), _r(2, "LAND", name="Venezia Santa Lucia"), _r(3, "LAND", name="Landgraaf"), _r(4, "ZZZ")]
        clean, _ = self._run(rows)
        got = {r[0]: r[1] for r in duckdb.sql(f"SELECT stop_id, station_code FROM '{clean}'").fetchall()}
        self.assertEqual(got, {1: "BERHBL", 2: "VENEZ", 3: "LAND", 4: "ZZZ"})

    def test_duplicate_stop_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self._run([_r(1, "AA"), _r(1, "BB")])


if __name__ == "__main__":
    unittest.main()