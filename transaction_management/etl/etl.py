"""Entry point for the stop ETL"""

import argparse
import logging
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    """Read KEY=VALUE lines of transaction_management/.env into os.environ"""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env(HERE.parent / ".env")  # before etl.config is imported: it reads DB_PASSWORD at import time

from etl import config, dump, extract, load, transform  # noqa: E402


def cmd_run(args) -> None:
    """Download, clean, and load the window into the central node only"""

    profile = extract.run_extract(args.year, args.date_from, args.date_to, force=args.force)
    clean = config.clean_path(args.year, args.date_from, args.date_to)
    t = transform.run_transform(Path(profile["staged"]), clean, profile)
    load.load_central(Path(t["clean"]), t["max_stop_id"], t["max_rdt_id"])
    print(f"OK node1 holds {t['rows']} rows. Next: have node1 fill node2/node3 (central/distribute.sql)")


def cmd_dump(args) -> None:
    """Snapshot the central node to a dump file"""

    result = dump.dump_central(Path(args.dir), args.via)
    print(f"Wrote {result['dump']} ({result['bytes'] / 1e6:.1f} MB)")


def cmd_restore(args) -> int:
    """Restore the central node from a dump."""

    existing = dump.existing_rows()
    if existing and not args.yes:
        print(f"node1 already has {existing} rows in `stop`; they will be replaced.")
        if input("Replace them with the dump? [y/N] ").strip().lower() != "y":
            print("Aborted, nothing changed.")
            return 1
    dump.restore_central(Path(args.dir), args.via)
    print("OK node1 restored. Next: have node1 fill node2/node3 (central/distribute.sql)")
    return 0


def main() -> int:
    """Parse the command line and run the chosen command"""
    
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="download, clean and load into the central node")
    run.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    run.add_argument("--date-from", default=config.DEFAULT_DATE_FROM, help="YYYY-MM-DD")
    run.add_argument("--date-to", default=config.DEFAULT_DATE_TO, help="YYYY-MM-DD")
    run.add_argument("--force", action="store_true", help="re-download even if the cached file is current")
    run.set_defaults(func=cmd_run)

    for name, func, help_ in (
        ("dump", cmd_dump, "snapshot the central node"),
        ("restore", cmd_restore, "restore the central node"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--dir", default=str(config.DUMP_DIR), help="dump folder (default: data/dumps)")
        sp.add_argument("--via", choices=["docker", "host"], default="docker", help="where pg_dump/pg_restore run")
        if name == "restore":
            sp.add_argument("-y", "--yes", action="store_true", help="replace existing rows without asking")
        sp.set_defaults(func=func)

    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())