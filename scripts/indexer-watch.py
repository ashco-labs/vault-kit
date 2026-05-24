#!/usr/bin/env python3
"""File watcher: re-index vault files when they change.

Polls every 10 seconds for .md files modified since the last check, then
calls index_file from indexer.py for each one. Designed to run forever
under pm2 (autorestart: true).

Usage:
    python3 indexer-watch.py [<vault-path>]
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from indexer import init_db, index_file


def get_db_path(vault_path: str) -> str:
    """Derive the default DB path for a vault (mirrors indexer.py logic)."""
    vault_name = os.path.basename(os.path.realpath(vault_path))
    return os.path.join(
        os.path.expanduser("~"), ".vault-index", f"{vault_name}.db"
    )


def watch(vault_path: str, db_path: str | None = None) -> None:
    if db_path is None:
        db_path = get_db_path(vault_path)

    db = init_db(db_path)
    last_check = time.time()

    print(f"Watching {vault_path} for changes (poll every 10s)")
    print(f"DB: {db_path}")

    skip_dirs = {".obsidian", ".git", ".vault-config", ".DS_Store", ".trash", ".stversions"}

    while True:
        time.sleep(10)
        now = time.time()
        changed = 0

        for root, dirs, files in os.walk(vault_path):
            # Skip hidden and known non-content dirs
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for f in files:
                if not f.endswith(".md"):
                    continue
                fp = os.path.join(root, f)
                try:
                    if os.path.getmtime(fp) > last_check:
                        if index_file(db, fp, vault_path):
                            changed += 1
                except (OSError, FileNotFoundError):
                    # File may have been deleted between walk and stat
                    continue

        if changed:
            db.commit()
            print(f"Re-indexed {changed} file(s)")

        last_check = now


if __name__ == "__main__":
    vault_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/ashco-vault")
    vault_path = os.path.realpath(vault_path)
    watch(vault_path)
