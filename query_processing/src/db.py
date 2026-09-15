"""
Functions for connecting to and managing the PostgreSQL database.
"""

import os
import subprocess
import time
from pathlib import Path

import psycopg

from src.config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    DUMP_FILE,
    SCHEMA_FILE,
)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        autocommit=True,
    )


def wait_for_db(max_retries: int = 15, delay: float = 2.0) -> bool:
    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    for attempt in range(1, max_retries + 1):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            print("Database connection established.")
            return True
        except Exception as e:
            if attempt == max_retries:
                print(f"Failed to connect after {max_retries} attempts: {e}")
                return False
            print(f"Waiting for database... ({attempt}/{max_retries})")
            time.sleep(delay)
    return False


def _run_sql_file(file_path: Path) -> bool:
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    if file_path.suffix.lower() == ".sql":
        cmd = [
            "psql",
            "-h",
            DB_HOST,
            "-p",
            str(DB_PORT),
            "-U",
            DB_USER,
            "-d",
            DB_NAME,
            "-f",
            str(file_path),
        ]
    else:
        cmd = [
            "pg_restore",
            "-h",
            DB_HOST,
            "-p",
            str(DB_PORT),
            "-U",
            DB_USER,
            "-d",
            DB_NAME,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            str(file_path),
        ]

    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            args=cmd, env=env, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            print(f"Error executing {file_path.name}:\n{result.stderr.strip() or result.stdout.strip()}")
            return False
        return True
    except Exception as e:
        print(f"Failed to execute {file_path.name}: {e}")
        return False


def restore_dump() -> bool:
    if not SCHEMA_FILE.exists() and not DUMP_FILE.exists():
        print(f"Neither schema file ({SCHEMA_FILE}) nor dump file ({DUMP_FILE}) found.")
        return False

    print("Resetting database schema (clean slate)...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DROP SCHEMA IF EXISTS public CASCADE;
                    CREATE SCHEMA public;
                    GRANT ALL ON SCHEMA public TO CURRENT_USER;
                    GRANT ALL ON SCHEMA public TO PUBLIC;
                """)
    except Exception as e:
        print(f"Error resetting database: {e}")
        return False

    if SCHEMA_FILE.exists():
        print(f"Applying schema: {SCHEMA_FILE.name}")
        if not _run_sql_file(SCHEMA_FILE):
            return False

    if DUMP_FILE.exists():
        print(f"Restoring dump: {DUMP_FILE.name}")
        if not _run_sql_file(DUMP_FILE):
            return False

    print("Database restored successfully.")
    return True
