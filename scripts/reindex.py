#!/usr/bin/env python3
"""Full re-index: drop tables and rebuild from scratch."""
import sys
import os

# Add scripts dir to path for indexer import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from indexer import run_index

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: reindex.py <vault-path> [--db <db-path>]")
        sys.exit(1)

    vault_path = sys.argv[1]
    db_path = None
    if "--db" in sys.argv:
        db_path = sys.argv[sys.argv.index("--db") + 1]

    run_index(vault_path, db_path, full=True)
