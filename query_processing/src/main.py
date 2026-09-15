"""
Main entry point for query benchmarking.
Expects baseline.sql and optimized.sql in each query directory.

# How To
Create a directory in `~/queries/`. Then create two sql files in that
directory.

- `baseline.sql`:   contains the dumb query ONLY.
- `optimized.sql`:  contains schema optimizations and an optimized
                    query. Do not worry about changing the database
                    schema in this file (like introducing indices)
                    as this file resets the dump per query pair.

The pseudocode fo the pipeline is below:
1. Get the query_pairs from each directory in `~/queries/`.
2. For each (baseline, optimized) in query_pairs.
    1. Setup the dump.
    2. Execute and time baseline.
    3. Execute and time optimized.
"""

import argparse
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.benchmark import (  
    benchmark_query_file,
    compute_metrics,
)
from src.config import QUERIES_DIR, RESULTS_DIR  
from src.db import get_connection, restore_dump, wait_for_db  
from src.util import clean_dir  


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Processing Performance Runner")
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Run only a specific query directory in queries/.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of measured benchmark iterations.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Number of warmup iterations.",
    )
    return parser.parse_args()


def print_summary_table(all_metrics: list[dict]) -> None:
    print("\nQUERY PERFORMANCE BENCHMARK SUMMARY")
    header = (
        f"{'Query':<30} | "
        f"{'Base (ms)':<11} | "
        f"{'Opt (ms)':<11} | "
        f"{'Speedup':<9} | "
        f"{'Base Cost':<11} | "
        f"{'Opt Cost':<11} | "
        f"{'Reduction':<9}"
    )
    print(header)
    for m in all_metrics:
        row = (
            f"{m['query_name']:<30} | "
            f"{m['baseline_median_exec_ms']:<11.2f} | "
            f"{m['optimized_median_exec_ms']:<11.2f} | "
            f"{m['speedup_ratio']:<8.2f}x | "
            f"{m['baseline_estimated_cost']:<11.2f} | "
            f"{m['optimized_estimated_cost']:<11.2f} | "
            f"{m['exec_time_reduction_pct']:<8.1f}%"
        )
        print(row)


def main() -> int:
    args = parse_args()

    if not wait_for_db():
        return 1

    query_dirs = []

    if args.query:
        target = QUERIES_DIR / args.query
        if not target.is_dir():
            print(f"Error: Query directory '{args.query}' not found in {QUERIES_DIR}")
            return 1
        if not (target / "baseline.sql").exists():
            print(f"Error: Query '{args.query}' is missing baseline.sql")
            return 1
        if not (target / "optimized.sql").exists():
            print(f"Error: Query '{args.query}' is missing optimized.sql")
            return 1
        query_dirs = [target]
    elif QUERIES_DIR.exists():
        for p in sorted(QUERIES_DIR.iterdir(), key=lambda p: p.name):
            if p.is_dir():
                has_baseline = (p / "baseline.sql").exists()
                has_optimized = (p / "optimized.sql").exists()
                if has_baseline and has_optimized:
                    query_dirs.append(p)
                elif has_baseline and not has_optimized:
                    print(f"Warning: Skipping '{p.name}' (missing optimized.sql)")
                elif has_optimized and not has_baseline:
                    print(f"Warning: Skipping '{p.name}' (missing baseline.sql)")

    if not query_dirs:
        print(f"No complete queries (with both baseline.sql and optimized.sql) found in {QUERIES_DIR}.")
        return 1

    clean_dir(RESULTS_DIR)
    print(f"Queries to benchmark: {[q.name for q in query_dirs]}")

    all_metrics = []

    for q_dir in query_dirs:
        baseline_file = q_dir / "baseline.sql"
        optimized_file = q_dir / "optimized.sql"

        print(f"\n  Processing Query: {q_dir.name}")

        print(" - [1 Setup] Restoring database from schema.sql and dump.sql...")
        if not restore_dump():
            print(f"Error restoring dump for {q_dir}.")
            return 1

        with get_connection() as conn:
            print(f" - [2 Baseline] Running baseline.sql ({args.warmup} warmup, {args.iterations} iterations)...")
            base_runs, base_plan = benchmark_query_file(
                conn, baseline_file, iterations=args.iterations, warmup=args.warmup
            )

            print(f" - [3 Optimized] Running optimized.sql ({args.warmup} warmup, {args.iterations} iterations)...")
            opt_runs, opt_plan = benchmark_query_file(
                conn, optimized_file, iterations=args.iterations, warmup=args.warmup
            )

            metrics = compute_metrics(q_dir.name, base_runs, opt_runs)
            all_metrics.append(metrics.to_dict())

            result_payload = {
                "metrics": metrics.to_dict(),
                "baseline_plan": base_plan,
                "optimized_plan": opt_plan,
            }
            result_file = RESULTS_DIR / f"{q_dir.name}.json"
            result_file.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

            print(
                f"  Result: {metrics.speedup_ratio}x speedup "
                f"({metrics.baseline_median_exec_ms:.2f}ms -> {metrics.optimized_median_exec_ms:.2f}ms, "
                f"{metrics.exec_time_reduction_pct:.1f}% reduction)"
            )

    if all_metrics:
        print_summary_table(all_metrics)

    return 0


if __name__ == "__main__":
    sys.exit(main())
