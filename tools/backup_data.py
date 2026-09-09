"""Consistent online SQLite backup; never overwrite an existing backup."""

import argparse
import os
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.database.is_file():
        raise SystemExit("Source database not found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(
        args.database.resolve().as_uri() + "?mode=ro", uri=True
    ) as source, sqlite3.connect(args.output) as target:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SystemExit("Backup integrity check failed: " + result)
    print("Backup verified: " + str(args.output.resolve()))


if __name__ == "__main__":
    main()
