"""
Main entry point.
"""

import argparse
import sys

from src.benchmark import execute_sql_file
from src.config import QUERIES_DIR, RESULTS_DIR
from src.db import get_connection, restore_dump, wait_for_db
from src.util import clean_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Processing Runner")
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


def main() -> int:
    args = parse_args()

    if not wait_for_db():
        return 1

    if not restore_dump():
        return 1

    query_dirs = []
    if args.query:
        target = QUERIES_DIR / args.query
        if target.is_dir() and (target / "baseline.sql").exists():
            query_dirs = [target]
        else:
            print(f"Error: Query '{args.query}' not found or lacks baseline.sql in {QUERIES_DIR}")
            return 1
    elif QUERIES_DIR.exists():
        query_dirs = sorted(
            [p for p in QUERIES_DIR.iterdir() if p.is_dir() and (p / "baseline.sql").exists()],
            key=lambda p: p.name,
        )

    if not query_dirs:
        print(f"No queries found in {QUERIES_DIR}.")
        return 0

    print(f"Discovered {len(query_dirs)} query directory(ies): {[q.name for q in query_dirs]}")

    with get_connection() as conn:
        for q_dir in query_dirs:
            baseline_file = q_dir / "baseline.sql"
            optimize_file = q_dir / "optimize.sql"
            optimized_file = q_dir / "optimized.sql"
            teardown_file = q_dir / "teardown.sql"

            print(f"Executing query: {q_dir.name}")
            execute_sql_file(conn, baseline_file)

            if optimize_file.exists():
                execute_sql_file(conn, optimize_file)

            if optimized_file.exists():
                execute_sql_file(conn, optimized_file)

            if teardown_file.exists():
                execute_sql_file(conn, teardown_file)

    clean_dir(RESULTS_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
