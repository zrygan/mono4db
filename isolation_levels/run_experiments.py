"""
Automates the transaction isolation levels and concurrency experiments

Uses the following SQL files:
  - dirty_read/dirtyread_A.sql & dirtyread_B.sql
  - non-repeatable_read/nrr_A.sql & nrr_B.sql
  - phantom_read/pr_A.sql & pr_B.sql

Note: A is the WRITER transaction (INSERT / UPDATE), B is the READER (SELECT).
"""

import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import mysql.connector
from mysql.connector import errorcode

# Default MySQL connection configuration
# Remember to replace # with YOUR MySQL values (we don't use Docker here).
DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "#"),
    "user": os.environ.get("MYSQL_USER", "#"),
    "password": os.environ.get("MYSQL_PASSWORD", "#"),
    "database": os.environ.get("MYSQL_DATABASE", "#"),
    "autocommit": True,
}

BASE_DIR = Path(__file__).resolve().parent

SQL_EXPERIMENTS = {
    "dirty_read": {
        "name": "Dirty Read",
        "dir": BASE_DIR / "dirty_read",
        "file_a": BASE_DIR / "dirty_read" / "dirtyread_A.sql",
        "file_b": BASE_DIR / "dirty_read" / "dirtyread_B.sql",
    },
    "non_repeatable_read": {
        "name": "Non-Repeatable Read",
        "dir": BASE_DIR / "non-repeatable_read",
        "file_a": BASE_DIR / "non-repeatable_read" / "nrr_A.sql",
        "file_b": BASE_DIR / "non-repeatable_read" / "nrr_B.sql",
    },
    "phantom_read": {
        "name": "Phantom Read",
        "dir": BASE_DIR / "phantom_read",
        "file_a": BASE_DIR / "phantom_read" / "pr_A.sql",
        "file_b": BASE_DIR / "phantom_read" / "pr_B.sql",
    },
}


@dataclass
class StatementEvent:
    txn: str
    statement: str
    start_offset: float
    duration: float
    affected_rows: Optional[int] = None
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    error: Optional[str] = None


@dataclass
class ScenarioResult:
    scenario_key: str
    scenario_name: str
    file_a: str
    file_b: str
    isolation_a: str
    isolation_b: str
    anomaly_detected: bool
    anomaly_type: str
    verdict: str
    diagnostic_details: str
    data_points: dict[str, Any] = field(default_factory=dict)
    events: list[StatementEvent] = field(default_factory=list)
    lock_wait_detected: bool = False
    errors: list[str] = field(default_factory=list)
    total_duration: float = 0.0


def get_connection(database: Optional[str] = None):
    cfg = DB_CONFIG.copy()
    if database:
        cfg["database"] = database
    return mysql.connector.connect(**cfg)


def verify_or_create_table():
    """
    Ensures simplified_film table exists in sakila with base data
    populated from film.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simplified_film (
            film_id INT PRIMARY KEY,
            title VARCHAR(255),
            release_year INT,
            length INT
        ) ENGINE=InnoDB;
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM simplified_film;")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute("""
            INSERT IGNORE INTO simplified_film (film_id, title, release_year, length)
            SELECT film_id, title, release_year, length FROM film;
        """)
        conn.commit()

    cur.execute("UPDATE simplified_film SET length = 86 WHERE film_id = 1;")
    cur.execute("DELETE FROM simplified_film WHERE film_id = 1001;")
    conn.commit()
    cur.close()
    conn.close()


def parse_sql_file(
    file_path: Path | str,
    sleep_seconds: Optional[float] = None,
) -> tuple[str, list[str]]:
    """
    Parses the SQL files into executable statements.

    Extracts the configured isolation level from the SQL file and
    optionally adjusts the DO SLEEP duration.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")

    content = path.read_text(encoding="utf-8")

    detected_iso = "UNKNOWN"
    iso_match = re.search(
        r"SET\s+SESSION\s+TRANSACTION\s+ISOLATION\s+LEVEL\s+([A-Za-z\s]+);",
        content,
        re.IGNORECASE,
    )
    if iso_match:
        detected_iso = iso_match.group(1).strip().upper()
        detected_iso = re.sub(r"--.*$", "", detected_iso).strip()

    clean_lines = []
    for line in content.splitlines():
        line_clean = re.sub(r"--.*$", "", line).strip()
        if line_clean:
            clean_lines.append(line_clean)

    full_sql = " ".join(clean_lines)

    if sleep_seconds is not None:
        full_sql = re.sub(
            r"DO\s+SLEEP\s*\(\s*\d+(\.\d+)?\s*\)",
            f"DO SLEEP({sleep_seconds})",
            full_sql,
            flags=re.IGNORECASE,
        )

    raw_statements = full_sql.split(";")
    statements = []
    for s in raw_statements:
        s_clean = s.strip()
        if s_clean:
            if s_clean.upper().startswith("USE "):
                continue
            statements.append(s_clean)

    return detected_iso, statements


def execute_transaction_thread(
    thread_label: str,
    statements: list[str],
    t0: float,
    events_list: list[StatementEvent],
    lock: threading.Lock,
    start_delay: float = 0.0,
):
    """
    Executes a parsed list of SQL statements.
    """
    if start_delay > 0:
        time.sleep(start_delay)

    conn = get_connection()
    cur = conn.cursor()

    for stmt in statements:
        start_offset = time.time() - t0
        stmt_t0 = time.time()
        err_msg = None
        rows = None
        cols = None
        aff_rows = None

        try:
            cur.execute(stmt)
            duration = time.time() - stmt_t0

            if cur.description:
                cols = [d[0] for d in cur.description]
                fetched = cur.fetchall()
                rows = [[col for col in row] for row in fetched]
            else:
                aff_rows = cur.rowcount

            stmt_upper = stmt.strip().upper()
            if stmt_upper == "COMMIT":
                conn.commit()
            elif stmt_upper == "ROLLBACK":
                conn.rollback()

        except mysql.connector.Error as err:
            duration = time.time() - stmt_t0
            err_msg = f"MySQL Error [{err.errno}]: {err.msg}"
            if err.errno in (errorcode.ER_LOCK_WAIT_TIMEOUT, errorcode.ER_LOCK_DEADLOCK):
                err_msg = f"LOCK CONFLICT [{err.errno}]: {err.msg}"

        event = StatementEvent(
            txn=thread_label,
            statement=stmt,
            start_offset=round(start_offset, 3),
            duration=round(duration, 3),
            affected_rows=aff_rows,
            columns=cols,
            rows=rows,
            error=err_msg,
        )

        with lock:
            events_list.append(event)

    try:
        cur.close()
        conn.close()
    except Exception:
        pass


def diagnose_dirty_read(
    events: list[StatementEvent],
    iso_b: str,
) -> tuple[bool, str, str, str, dict[str, Any]]:
    """Analyzes execution events for Dirty Read anomaly."""
    pre_rollback_length = None
    post_rollback_length = None
    txn_b_blocked = False

    for ev in events:
        if ev.txn == "Txn B" and ev.rows is not None and len(ev.rows) > 0:
            for row in ev.rows:
                if len(row) >= 2 and isinstance(row[0], str):
                    if "pre-rollback" in row[0].lower():
                        pre_rollback_length = row[1]
                    elif "post-rollback" in row[0].lower():
                        post_rollback_length = row[1]
                elif len(row) == 1 and isinstance(row[0], (int, float)):
                    if pre_rollback_length is None:
                        pre_rollback_length = row[0]
                    else:
                        post_rollback_length = row[0]

        if ev.txn == "Txn B" and ev.duration >= 1.0 and "SELECT" in ev.statement.upper():
            txn_b_blocked = True

    data_points = {
        "pre_rollback_length": pre_rollback_length,
        "post_rollback_length": post_rollback_length,
        "txn_b_blocked": txn_b_blocked,
    }

    if pre_rollback_length == 5:
        anomaly = True
        atype = "DIRTY_READ"
        verdict = "DIRTY READ DETECTED"
        diag = (
            f"Txn B read uncommitted length={pre_rollback_length} under {iso_b}. "
            f"Txn A subsequently rolled back (reverting length to {post_rollback_length}). "
            f"Txn B operated on invalid data that was never committed to the database."
        )
    else:
        anomaly = False
        atype = "NONE"
        verdict = "DIRTY READ PREVENTED"
        if txn_b_blocked:
            diag = (
                f"Txn B was blocked by exclusive lock held by Txn A under {iso_b}. "
                f"Txn B waited until Txn A rolled back, safely reading committed length={pre_rollback_length}."
            )
        else:
            diag = (
                f"Under {iso_b}, Txn B performed a consistent snapshot read, reading committed length={pre_rollback_length} "
                f"and ignoring Txn A's uncommitted change to 5."
            )

    return anomaly, atype, verdict, diag, data_points


def diagnose_non_repeatable_read(
    events: list[StatementEvent],
    iso_a: str,
) -> tuple[bool, str, str, str, dict[str, Any]]:
    """Analyzes execution events for Non-Repeatable Read anomaly."""
    pre_commit_length = None
    post_commit_length = None
    txn_b_blocked = False

    for ev in events:
        if ev.txn == "Txn A" and ev.rows is not None and len(ev.rows) > 0:
            for row in ev.rows:
                if len(row) >= 2 and isinstance(row[0], str):
                    if "pre-commit" in row[0].lower():
                        pre_commit_length = row[1]
                    elif "post-commit" in row[0].lower():
                        post_commit_length = row[1]
                elif len(row) == 1 and isinstance(row[0], (int, float)):
                    if pre_commit_length is None:
                        pre_commit_length = row[0]
                    else:
                        post_commit_length = row[0]

        if ev.txn == "Txn B" and ev.duration >= 1.0 and "UPDATE" in ev.statement.upper():
            txn_b_blocked = True

    data_points = {
        "pre_commit_length": pre_commit_length,
        "post_commit_length": post_commit_length,
        "txn_b_blocked": txn_b_blocked,
    }

    if pre_commit_length is not None and post_commit_length is not None and pre_commit_length != post_commit_length:
        anomaly = True
        atype = "NON_REPEATABLE_READ"
        verdict = "NON-REPEATABLE READ DETECTED"
        diag = (
            f"Within Txn A ({iso_a}), repeated reads of the same row yielded different values: "
            f"initial length={pre_commit_length}, but after Txn B committed an update, length={post_commit_length}."
        )
    else:
        anomaly = False
        atype = "NONE"
        verdict = "NON-REPEATABLE READ PREVENTED"
        if txn_b_blocked:
            diag = (
                f"Under {iso_a}, Txn A acquired a shared lock. Txn B's UPDATE was blocked until Txn A completed. "
                f"Txn A observed consistent length={pre_commit_length} across all reads."
            )
        else:
            diag = (
                f"Under {iso_a}, MVCC snapshot isolation ensured repeated reads saw consistent length={pre_commit_length}, "
                f"even after Txn B committed length=5."
            )

    return anomaly, atype, verdict, diag, data_points


def diagnose_phantom_read(
    events: list[StatementEvent],
    iso_a: str,
) -> tuple[bool, str, str, str, dict[str, Any]]:
    """Analyzes execution events for Phantom Read anomaly."""
    pre_insert_count = None
    post_insert_count = None
    txn_b_blocked = False

    for ev in events:
        if ev.txn == "Txn A" and ev.rows is not None and len(ev.rows) > 0:
            for row in ev.rows:
                if len(row) >= 2 and isinstance(row[0], str):
                    if "pre-insert" in row[0].lower():
                        pre_insert_count = row[1]
                    elif "post-insert" in row[0].lower():
                        post_insert_count = row[1]
                elif len(row) == 1 and isinstance(row[0], int):
                    if pre_insert_count is None:
                        pre_insert_count = row[0]
                    else:
                        post_insert_count = row[0]

        if ev.txn == "Txn B" and ev.duration >= 1.0 and "INSERT" in ev.statement.upper():
            txn_b_blocked = True

    data_points = {
        "pre_insert_count": pre_insert_count,
        "post_insert_count": post_insert_count,
        "txn_b_blocked": txn_b_blocked,
    }

    if pre_insert_count is not None and post_insert_count is not None and post_insert_count > pre_insert_count:
        anomaly = True
        atype = "PHANTOM_READ"
        verdict = "PHANTOM READ DETECTED"
        diag = (
            f"Within Txn A ({iso_a}), repeated range/count queries yielded different row counts: "
            f"pre-insert count={pre_insert_count}, post-insert count={post_insert_count} "
            f"(phantom row 1001 inserted & committed by Txn B appeared mid-transaction)."
        )
    else:
        anomaly = False
        atype = "NONE"
        verdict = "PHANTOM READ PREVENTED"
        if txn_b_blocked:
            diag = (
                f"Under {iso_a}, range/gap locking blocked Txn B's INSERT until Txn A completed. "
                f"Count remained stable at {pre_insert_count}."
            )
        else:
            diag = (
                f"Under {iso_a}, MVCC snapshot isolation shielded Txn A from newly committed rows. "
                f"Count remained stable at {pre_insert_count}."
            )

    return anomaly, atype, verdict, diag, data_points


def run_scenario(
    scenario_key: str,
    sleep_seconds: float = 1.5,
    b_start_delay: float = 0.5,
) -> ScenarioResult:
    """
    Loads SQL files for the given scenario, executes them concurrently in two threads,
    and returns a structured ScenarioResult with anomaly diagnostics.
    """
    if scenario_key not in SQL_EXPERIMENTS:
        raise ValueError(f"Unknown scenario: {scenario_key}. Choose from {list(SQL_EXPERIMENTS.keys())}")

    scenario_info = SQL_EXPERIMENTS[scenario_key]
    file_a = scenario_info["file_a"]
    file_b = scenario_info["file_b"]

    verify_or_create_table()

    iso_a, stmts_a = parse_sql_file(file_a, sleep_seconds=sleep_seconds)
    iso_b, stmts_b = parse_sql_file(file_b, sleep_seconds=sleep_seconds)

    events: list[StatementEvent] = []
    events_lock = threading.Lock()
    t0 = time.time()

    t1 = threading.Thread(
        target=execute_transaction_thread,
        args=("Txn A", stmts_a, t0, events, events_lock, 0.0),
        name="Txn_A",
    )
    t2 = threading.Thread(
        target=execute_transaction_thread,
        args=("Txn B", stmts_b, t0, events, events_lock, b_start_delay),
        name="Txn_B",
    )

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    total_duration = round(time.time() - t0, 3)

    events.sort(key=lambda e: (e.start_offset, e.duration))

    errors = [e.error for e in events if e.error]
    lock_wait = any(e.duration >= (sleep_seconds * 0.8) for e in events if "SLEEP" not in e.statement.upper())

    if scenario_key == "dirty_read":
        anomaly, atype, verdict, diag, data_points = diagnose_dirty_read(events, iso_b)
    elif scenario_key == "non_repeatable_read":
        anomaly, atype, verdict, diag, data_points = diagnose_non_repeatable_read(events, iso_a)
    elif scenario_key == "phantom_read":
        anomaly, atype, verdict, diag, data_points = diagnose_phantom_read(events, iso_a)
    else:
        anomaly = False
        atype = "NONE"
        verdict = "COMPLETED"
        diag = "Execution finished."
        data_points = {}

    return ScenarioResult(
        scenario_key=scenario_key,
        scenario_name=scenario_info["name"],
        file_a=str(file_a),
        file_b=str(file_b),
        isolation_a=iso_a,
        isolation_b=iso_b,
        anomaly_detected=anomaly,
        anomaly_type=atype,
        verdict=verdict,
        diagnostic_details=diag,
        data_points=data_points,
        events=events,
        lock_wait_detected=lock_wait,
        errors=errors,
        total_duration=total_duration,
    )


def print_scenario_report(result: ScenarioResult):
    """Prints a human-readable diagnostic report for a scenario execution."""
    print("=" * 80)
    print(f"SCENARIO: {result.scenario_name.upper()}  [{result.verdict}]")
    print(f"SQL Files: A: {Path(result.file_a).name} | B: {Path(result.file_b).name}")
    print(f"Isolation: Txn A = {result.isolation_a} | Txn B = {result.isolation_b}")
    print(f"Runtime:   {result.total_duration:.2f}s | Lock Wait Observed: {result.lock_wait_detected}")
    print("=" * 80)

    print("\n--- Statement Execution Trace (Chronological) ---")
    print(f"{'Time':>6} | {'Thread':<6} | {'Duration':>8} | {'Statement / Result'}")
    print("-" * 80)
    for ev in result.events:
        res_summary = ""
        if ev.error:
            res_summary = f" [ERROR: {ev.error}]"
        elif ev.rows is not None:
            res_summary = f" -> {ev.rows}"
        elif ev.affected_rows is not None and ev.affected_rows >= 0:
            res_summary = f" (affected: {ev.affected_rows})"

        stmt_preview = ev.statement
        if len(stmt_preview) > 50:
            stmt_preview = stmt_preview[:47] + "..."
        print(f"{ev.start_offset:>5.2f}s | {ev.txn:<6} | {ev.duration:>7.2f}s | {stmt_preview}{res_summary}")

    print("\n--- Diagnostic Findings ---")
    print(f"Status:   {'[!] ANOMALY CONFIRMED' if result.anomaly_detected else '[OK] ANOMALY PREVENTED'}")
    print(f"Type:     {result.anomaly_type}")
    print(f"Data:     {result.data_points}")
    print(f"Details:  {result.diagnostic_details}")
    if result.errors:
        print(f"Errors:   {result.errors}")
    print("-" * 80)
    print()


def main() -> None:
    verify_or_create_table()

    for scenario_key in SQL_EXPERIMENTS:
        res = run_scenario(scenario_key)
        print_scenario_report(res)


if __name__ == "__main__":
    main()
