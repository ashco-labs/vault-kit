#!/usr/bin/env python3
"""vault-kit daemon: single process running all vault maintenance tasks.

Replaces four separate pm2 processes with one long-running script using
internal timers:

  - File-watch indexing (every 10s): poll for modified .md files, re-index
  - Full incremental index (every 10 min): walk entire vault, catch drift
  - Auto-sweep git commit (every 1h): commit uncommitted vault changes
  - Chat-synth (every 30 min): generate session digests from JSONL transcripts

Usage:
    python3 daemon.py <vault-path> [--device-id <id>]

Standalone: runs without pm2. Logs to stdout. Handles SIGTERM/SIGINT.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

# Make sibling scripts importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from indexer import (
    SKIP_DIRS,
    index_file,
    init_db,
    run_index,
    walk_vault,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _get_db_path(vault_path: str) -> str:
    """Derive the default DB path for a vault (same logic as indexer-watch.py)."""
    vault_name = os.path.basename(os.path.realpath(vault_path))
    return os.path.join(
        os.path.expanduser("~"), ".vault-index", f"{vault_name}.db"
    )


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------


class VaultDaemon:
    def __init__(self, vault_path: str, device_id: str = "default"):
        self.vault_path = os.path.realpath(os.path.expanduser(vault_path))
        self.device_id = device_id
        self.db_path = _get_db_path(self.vault_path)
        self.running = True
        self.last_file_check = time.time()
        self.scripts_dir = os.path.dirname(os.path.abspath(__file__))

        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        print(f"\n[{_ts()}] Shutting down (signal {signum})...")
        self.running = False

    # ----- File-watch (every 10s) ------------------------------------------

    def _task_file_watch(self) -> None:
        """Re-index .md files modified since last check."""
        try:
            db = init_db(self.db_path)
            now = time.time()
            changed = 0

            for root, dirs, files in os.walk(self.vault_path):
                dirs[:] = [
                    d for d in dirs
                    if d not in SKIP_DIRS and not d.startswith(".")
                ]
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    fp = os.path.join(root, f)
                    try:
                        if os.path.getmtime(fp) > self.last_file_check:
                            if index_file(db, fp, self.vault_path):
                                changed += 1
                    except (OSError, FileNotFoundError):
                        continue

            if changed:
                db.commit()
                print(f"[{_ts()}] file-watch: re-indexed {changed} file(s)")

            self.last_file_check = now
            db.close()
        except Exception as e:
            print(f"[{_ts()}] file-watch error: {e}", file=sys.stderr)

    # ----- Full incremental index (every 10 min) ---------------------------

    def _task_full_index(self) -> None:
        """Run a full vault walk to catch anything file-watch missed."""
        try:
            print(f"[{_ts()}] full-index: starting incremental scan...")
            run_index(self.vault_path, self.db_path, full=False)
            print(f"[{_ts()}] full-index: done")
        except Exception as e:
            print(f"[{_ts()}] full-index error: {e}", file=sys.stderr)

    # ----- Auto-sweep git commit (every 1h) --------------------------------

    def _task_auto_sweep(self) -> None:
        """Check git status in the vault and commit any uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=self.vault_path,
            )
            dirty_lines = [
                l for l in result.stdout.strip().splitlines() if l.strip()
            ]
            if not dirty_lines:
                print(f"[{_ts()}] auto-sweep: nothing to commit")
                return

            n = len(dirty_lines)
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.vault_path,
                check=True,
            )
            subprocess.run(
                [
                    "git", "commit",
                    "--author=Auto-Sweep <sweep@local>",
                    "-m", f"chore(vault): auto-sweep -- {n} files",
                ],
                cwd=self.vault_path,
                check=True,
            )
            print(f"[{_ts()}] auto-sweep: committed {n} files")
        except Exception as e:
            print(f"[{_ts()}] auto-sweep error: {e}", file=sys.stderr)

    # ----- Chat-synth (every 30 min) ---------------------------------------

    def _task_chat_synth(self) -> None:
        """Synthesize JSONL transcripts into vault session digests."""
        try:
            print(f"[{_ts()}] chat-synth: starting...")
            # chat-synth.py has a hyphen, so use importlib for the import
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "chat_synth",
                os.path.join(self.scripts_dir, "chat-synth.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run(self.vault_path, self.device_id)
            print(f"[{_ts()}] chat-synth: done")
        except Exception as e:
            print(f"[{_ts()}] chat-synth error: {e}", file=sys.stderr)

    # ----- Main loop -------------------------------------------------------

    def run(self) -> None:
        print(f"vault-kit daemon started")
        print(f"  vault:     {self.vault_path}")
        print(f"  device:    {self.device_id}")
        print(f"  db:        {self.db_path}")
        print(f"  schedules: file-watch=10s, index=10m, sweep=1h, synth=30m")
        print()

        # Run all tasks once at startup, then on schedule
        last_index = 0
        last_sweep = 0
        last_synth = 0

        while self.running:
            now = time.time()

            # File-watch: every 10s (runs each loop iteration)
            self._task_file_watch()

            # Full index: every 10 min
            if now - last_index >= 600:
                self._task_full_index()
                last_index = now

            # Auto-sweep: every hour
            if now - last_sweep >= 3600:
                self._task_auto_sweep()
                last_sweep = now

            # Chat-synth: every 30 min
            if now - last_synth >= 1800:
                self._task_chat_synth()
                last_synth = now

            # Sleep 10s between polls, checking for shutdown each second
            for _ in range(10):
                if not self.running:
                    break
                time.sleep(1)

        print(f"[{_ts()}] Daemon stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="vault-kit daemon: single process for all vault maintenance"
    )
    parser.add_argument("vault_path", help="Path to the vault root directory")
    parser.add_argument(
        "--device-id",
        default=os.environ.get("VAULT_DEVICE_ID", "default"),
        help="Device identifier (default: VAULT_DEVICE_ID env or 'default')",
    )
    args = parser.parse_args()

    if not os.path.isdir(os.path.expanduser(args.vault_path)):
        print(
            f"Error: vault path does not exist: {args.vault_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    daemon = VaultDaemon(args.vault_path, args.device_id)
    daemon.run()


if __name__ == "__main__":
    main()
