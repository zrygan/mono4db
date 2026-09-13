"""
Data classes and functions for benchmarking metrics.

# Future

Perhaps in the future we can consider adding Postgre's EXPLAIN command
(see: https://www.postgresql.org/docs/current/sql-explain.html).
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg


@dataclass
class QueryRun:
    execution_time_ms: float
    planning_time_ms: float
    shared_hit_blocks: int
    shared_read_blocks: int
    root_node_type: str
    plan_dict: dict[str, Any]


@dataclass
class Metrics:
    query_name: str
    baseline_median_exec_ms: float
    baseline_mean_exec_ms: float
    baseline_planning_ms: float
    baseline_shared_hits: int
    baseline_shared_reads: int
    baseline_root_node: str

    optimized_median_exec_ms: float
    optimized_mean_exec_ms: float
    optimized_planning_ms: float
    optimized_shared_hits: int
    optimized_shared_reads: int
    optimized_root_node: str

    speedup_ratio: float
    exec_time_reduction_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def execute_sql_file(conn: psycopg.Connection, file_path: Path) -> None:
    content = file_path.read_text(encoding="utf-8").strip()
    if content:
        with conn.cursor() as cur:
            cur.execute(content)
