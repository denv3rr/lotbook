"""Verify an encrypted backup into a NEW file, without activating it."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.recovery import MAX_DATABASE_BYTES, restore_to_new_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path, help="New staging database file; never an existing database")
    args = parser.parse_args()
    try:
        if args.archive.stat().st_size > MAX_DATABASE_BYTES + 16384:
            raise ValueError("Backup exceeds this release's size limit.")
        password = getpass.getpass("Backup passphrase (not displayed): ")
        manifest = restore_to_new_file(args.archive.read_bytes(), password, args.destination)
    except (OSError, ValueError, sqlite3.Error) as failure:
        parser.exit(1, f"Recovery not staged: {failure}\n")
    print(f"Verified recovery candidate: {args.destination.resolve()}")
    print(f"Snapshot timestamp: {manifest['created_at']}")
    print(f"SHA-256: {manifest['sha256']}")
    print("The running database was NOT replaced. Protect this plaintext candidate.")


if __name__ == "__main__":
    main()
