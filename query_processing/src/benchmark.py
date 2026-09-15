"""
Data classes and functions for benchmarking metrics and EXPLAIN analysis.
"""

import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg


@dataclass
class QueryRun:
    execution_time_ms: float
    planning_time_ms: float
    estimated_cost: float
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
    baseline_estimated_cost: float
    baseline_shared_hits: int
    baseline_shared_reads: int
    baseline_root_node: str

    optimized_median_exec_ms: float
    optimized_mean_exec_ms: float
    optimized_planning_ms: float
    optimized_estimated_cost: float
    optimized_shared_hits: int
    optimized_shared_reads: int
    optimized_root_node: str

    speedup_ratio: float
    exec_time_reduction_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_sql_statements(sql_content: str) -> tuple[list[str], str]:
    """
    Split SQL script into setup statements (e.g. DDL / CREATE INDEX executed once)
    and the final query to be benchmarked with EXPLAIN ANALYZE.
    """
    lines = []
    for line in sql_content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("--"):
            lines.append(line)
    clean_text = "\n".join(lines).strip()

    raw_statements = [s.strip() for s in clean_text.split(";") if s.strip()]
    if not raw_statements:
        return [], ""

    setup_statements = raw_statements[:-1]
    target_query = raw_statements[-1]
    return setup_statements, target_query


def explain_analyze_query(conn: psycopg.Connection, sql: str) -> QueryRun:
    """Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) and extract performance metrics."""
    clean_sql = sql.strip().rstrip(";")
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {clean_sql};"

    with conn.cursor() as cur:
        cur.execute(explain_sql)
        row = cur.fetchone()
        data = row[0] if row else []
        query_info = data[0] if isinstance(data, list) and data else {}

    plan = query_info.get("Plan", {})
    return QueryRun(
        execution_time_ms=query_info.get("Execution Time", 0.0),
        planning_time_ms=query_info.get("Planning Time", 0.0),
        estimated_cost=plan.get("Total Cost", 0.0),
        shared_hit_blocks=plan.get("Shared Hit Blocks", 0),
        shared_read_blocks=plan.get("Shared Read Blocks", 0),
        root_node_type=plan.get("Node Type", "Unknown"),
        plan_dict=query_info,
    )


def benchmark_query_file(
    conn: psycopg.Connection, file_path: Path, iterations: int = 3, warmup: int = 1
) -> tuple[list[QueryRun], dict[str, Any]]:
    """
    Execute any setup statements (e.g. CREATE INDEX in optimized.sql) once,
    then benchmark the target query with warmup and measured iterations.
    """
    sql = file_path.read_text(encoding="utf-8")
    setup_stmts, target_query = parse_sql_statements(sql)

    if setup_stmts:
        with conn.cursor() as cur:
            for stmt in setup_stmts:
                cur.execute(stmt)

    if not target_query:
        raise ValueError(f"No executable query found in {file_path}")

    for _ in range(warmup):
        explain_analyze_query(conn, target_query)

    runs: list[QueryRun] = []
    for _ in range(iterations):
        runs.append(explain_analyze_query(conn, target_query))

    last_plan = runs[-1].plan_dict if runs else {}
    return runs, last_plan


def compute_metrics(
    query_name: str,
    baseline_runs: list[QueryRun],
    optimized_runs: list[QueryRun],
) -> Metrics:
    """Calculate aggregated metrics comparing baseline against optimized runs."""
    base_execs = [r.execution_time_ms for r in baseline_runs]
    opt_execs = [r.execution_time_ms for r in optimized_runs]

    base_med = statistics.median(base_execs)
    opt_med = statistics.median(opt_execs)

    speedup = round(base_med / opt_med, 2) if opt_med > 0 else 1.0
    reduction = round(((base_med - opt_med) / base_med) * 100.0, 2) if base_med > 0 else 0.0

    return Metrics(
        query_name=query_name,
        baseline_median_exec_ms=round(base_med, 2),
        baseline_mean_exec_ms=round(statistics.mean(base_execs), 2),
        baseline_planning_ms=round(statistics.mean([r.planning_time_ms for r in baseline_runs]), 2),
        baseline_estimated_cost=round(baseline_runs[-1].estimated_cost, 2),
        baseline_shared_hits=baseline_runs[-1].shared_hit_blocks,
        baseline_shared_reads=baseline_runs[-1].shared_read_blocks,
        baseline_root_node=baseline_runs[-1].root_node_type,

        optimized_median_exec_ms=round(opt_med, 2),
        optimized_mean_exec_ms=round(statistics.mean(opt_execs), 2),
        optimized_planning_ms=round(statistics.mean([r.planning_time_ms for r in optimized_runs]), 2),
        optimized_estimated_cost=round(optimized_runs[-1].estimated_cost, 2),
        optimized_shared_hits=optimized_runs[-1].shared_hit_blocks,
        optimized_shared_reads=optimized_runs[-1].shared_read_blocks,
        optimized_root_node=optimized_runs[-1].root_node_type,

        speedup_ratio=speedup,
        exec_time_reduction_pct=reduction,
    )
