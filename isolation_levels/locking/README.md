# How to run

From the repository root, open PowerShell and run:

```powershell
cd isolation_levels/locking
uv run python run_locking_experiments.py
```

Enter the MySQL password when prompted. Defaults: host `127.0.0.1`, port `3306`, user `root`, database `sakila`.

To use the existing Python environment directly from this folder:

```powershell
..\.venv\Scripts\python.exe run_locking_experiments.py
```

Optional commands:

```powershell
# Run each experiment twice (default: once).
uv run python run_locking_experiments.py --repeat 2

# Run one experiment.
uv run python run_locking_experiments.py --case ru_dirty

# Check SQL parsing without connecting to MySQL.
uv run python run_locking_experiments.py --validate-only
```

Available cases: `ru_dirty`, `rc_repeatable`, `rr_phantom`, and `serial_table`.

For a different database connection, set `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, or `MYSQL_DATABASE` before running.

Each run overwrites `locking.json` and `locking_results.md` in this folder.

## TLDR
Use the first set of commands to run.
