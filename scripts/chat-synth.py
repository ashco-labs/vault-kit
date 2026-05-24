#!/usr/bin/env python3
"""chat-synth: scan Claude Code JSONL session transcripts, generate session
digests in Agent/Sessions/<device-id>/.

Idempotent: running twice on the same unchanged transcript produces no changes.

Usage:
    python3 chat-synth.py [--vault <path>] [--device-id <id>]
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JSONL_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
ACTIVE_THRESHOLD_SECONDS = 30 * 60  # skip files modified <30 min ago
MIN_USER_TURNS = 3  # skip transcripts with fewer real user turns (filters out subprocess calls)
MIN_DURATION_SECONDS = 60  # skip sessions shorter than 1 minute
PATH_PATTERNS = re.compile(
    r"(?:"
    r"~/repos/[\w./-]+"
    r"|/Users/[\w./-]+"
    r"|~/ashco-vault/[\w./-]+"
    r"|~/[\w./-]{3,}"
    r")"
)

# Project path substrings that indicate subprocess/cron JSONL, not interactive sessions.
# These create tiny transcripts (1-2 turns) that aren't worth digesting.
SKIP_PROJECT_PATTERNS = [
    "-workers-reader-sync",      # reader-sync AI tag generation (claude -p)
    "-workers-scheduled-scripts", # codify-reflection cron
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_path(path: str) -> str:
    """Stable 8-char hex hash of a file path (for dedup + filenames)."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]


def slugify(text: str, max_len: int = 40) -> str:
    """Turn text into a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len].rstrip("-")


def extract_text_from_content(content) -> str:
    """Pull plain text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result" and isinstance(
                    block.get("content"), str
                ):
                    parts.append(block["content"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------


def parse_transcript(jsonl_path: str) -> dict | None:
    """Parse a JSONL transcript, returning a summary dict or None on failure."""
    user_messages = []
    assistant_messages = []
    all_timestamps = []
    all_text = ""

    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Extract timestamp from any line that has one
                ts = obj.get("timestamp")
                if ts:
                    all_timestamps.append(ts)

                msg = obj.get("message")
                if not isinstance(msg, dict):
                    # Top-level type=user entries (initial prompt)
                    if obj.get("type") == "user" and isinstance(
                        obj.get("content"), str
                    ):
                        text = obj["content"]
                        if text and len(text) > 1:
                            user_messages.append(text)
                            all_text += text + "\n"
                    continue

                role = msg.get("role")
                content = msg.get("content")
                text = extract_text_from_content(content)

                if role == "user":
                    # Filter out tool_result-only turns (not real user input)
                    if isinstance(content, list) and all(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    ):
                        continue
                    if text.strip():
                        user_messages.append(text.strip())
                        all_text += text + "\n"
                elif role == "assistant":
                    if text.strip():
                        assistant_messages.append(text.strip())
                        all_text += text + "\n"
    except Exception as e:
        print(f"  [error] Failed to parse {jsonl_path}: {e}", file=sys.stderr)
        return None

    if not user_messages:
        return None

    # Objective: first real user message (skip very short ones like "doc")
    objective = "Untitled session"
    for msg in user_messages:
        cleaned = msg.strip()
        if len(cleaned) > 5:
            # Truncate long objectives
            if len(cleaned) > 120:
                objective = cleaned[:117] + "..."
            else:
                objective = cleaned
            break

    # Timestamps
    first_ts = all_timestamps[0] if all_timestamps else None
    last_ts = all_timestamps[-1] if all_timestamps else None
    duration = ""
    if first_ts and last_ts:
        try:
            t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            delta = t1 - t0
            total_min = int(delta.total_seconds() / 60)
            if total_min < 1:
                duration = "<1 min"
            elif total_min < 60:
                duration = f"{total_min} min"
            else:
                hours = total_min // 60
                mins = total_min % 60
                duration = f"{hours}h {mins}m" if mins else f"{hours}h"
        except (ValueError, TypeError):
            pass

    # File paths mentioned
    paths_found = set(PATH_PATTERNS.findall(all_text))
    # Normalize and deduplicate
    paths_found = sorted(set(p.rstrip("/.,:;)") for p in paths_found))[:20]

    return {
        "objective": objective,
        "user_turns": len(user_messages),
        "assistant_turns": len(assistant_messages),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "duration": duration,
        "file_paths": paths_found,
    }


# ---------------------------------------------------------------------------
# Digest writing
# ---------------------------------------------------------------------------


def build_digest(summary: dict, jsonl_path: str) -> str:
    """Build a markdown digest from the parsed summary."""
    obj = summary["objective"]
    # Title: first line of objective, cleaned up
    title_line = obj.split("\n")[0][:100]

    created = ""
    session_started = ""
    if summary["first_ts"]:
        try:
            dt = datetime.fromisoformat(
                summary["first_ts"].replace("Z", "+00:00")
            )
            created = dt.strftime("%Y-%m-%d")
            session_started = summary["first_ts"]
        except (ValueError, TypeError):
            created = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not created:
        created = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "---",
        f'title: "{title_line}"',
        "type: session",
        "source: chat-synth",
        f"created: {created}",
        f"session_started: {session_started}" if session_started else None,
        f'duration: "{summary["duration"]}"' if summary["duration"] else None,
        "notes_created: []",
        f"transcript: {jsonl_path}",
        "---",
        "",
        "## Objective",
        "",
        obj,
        "",
        "## Stats",
        "",
        f"- User turns: {summary['user_turns']}",
        f"- Assistant turns: {summary['assistant_turns']}",
    ]

    if summary["duration"]:
        lines.append(f"- Duration: {summary['duration']}")

    if summary["file_paths"]:
        lines.append("")
        lines.append("## Files touched")
        lines.append("")
        for p in summary["file_paths"]:
            lines.append(f"- `{p}`")

    lines.append("")
    return "\n".join(l for l in lines if l is not None)


def digest_path_for(
    vault_path: str, device_id: str, jsonl_path: str, summary: dict
) -> str:
    """Compute the output path for a digest file."""
    h = hash_path(jsonl_path)
    slug = slugify(summary["objective"].split("\n")[0][:40]) or "session"

    date_str = ""
    if summary["first_ts"]:
        try:
            dt = datetime.fromisoformat(
                summary["first_ts"].replace("Z", "+00:00")
            )
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    filename = f"{date_str}-{slug}-{h}.md"
    return os.path.join(vault_path, "Agent", "Sessions", device_id, filename)


def find_existing_digest(
    vault_path: str, device_id: str, jsonl_path: str
) -> str | None:
    """Find an existing digest for a given transcript (by path hash)."""
    h = hash_path(jsonl_path)
    sessions_dir = os.path.join(vault_path, "Agent", "Sessions", device_id)
    if not os.path.isdir(sessions_dir):
        return None
    for fname in os.listdir(sessions_dir):
        if fname.endswith(f"-{h}.md"):
            return os.path.join(sessions_dir, fname)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(vault_path: str, device_id: str) -> None:
    vault_path = os.path.realpath(os.path.expanduser(vault_path))
    now = time.time()

    jsonl_files = glob.glob(JSONL_GLOB)
    if not jsonl_files:
        print("No JSONL transcript files found.")
        return

    print(f"Vault:     {vault_path}")
    print(f"Device:    {device_id}")
    print(f"Transcripts found: {len(jsonl_files)}")
    print()

    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for jsonl_path in sorted(jsonl_files):
        jsonl_path = os.path.realpath(jsonl_path)

        # Skip active sessions (modified <30 min ago)
        mtime = os.path.getmtime(jsonl_path)
        if (now - mtime) < ACTIVE_THRESHOLD_SECONDS:
            skipped += 1
            continue

        # Skip known subprocess/cron project paths
        if any(pat in jsonl_path for pat in SKIP_PROJECT_PATTERNS):
            skipped += 1
            continue

        # Check for existing digest
        existing = find_existing_digest(vault_path, device_id, jsonl_path)
        if existing:
            # Skip if transcript hasn't changed since digest was written
            digest_mtime = os.path.getmtime(existing)
            if mtime <= digest_mtime:
                skipped += 1
                continue

        # Parse transcript
        summary = parse_transcript(jsonl_path)
        if summary is None:
            skipped += 1
            continue

        # Skip trivial sessions (subprocess calls, 1-shot prompts)
        if summary["user_turns"] < MIN_USER_TURNS:
            skipped += 1
            continue

        # Skip very short sessions
        if summary["first_ts"] and summary["last_ts"]:
            try:
                t0 = datetime.fromisoformat(summary["first_ts"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(summary["last_ts"].replace("Z", "+00:00"))
                if (t1 - t0).total_seconds() < MIN_DURATION_SECONDS:
                    skipped += 1
                    continue
            except (ValueError, TypeError):
                pass

        # Build and write digest
        digest_content = build_digest(summary, jsonl_path)
        out_path = digest_path_for(vault_path, device_id, jsonl_path, summary)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(digest_content)

            if existing and existing != out_path:
                # Slug or date changed, remove old file
                os.remove(existing)
                updated += 1
                print(f"  Updated: {os.path.basename(out_path)}")
            elif existing:
                updated += 1
                print(f"  Updated: {os.path.basename(out_path)}")
            else:
                created += 1
                print(f"  Created: {os.path.basename(out_path)}")
        except Exception as e:
            print(f"  [error] Writing {out_path}: {e}", file=sys.stderr)
            errors += 1

    print()
    print(f"Created: {created}  Updated: {updated}  Skipped: {skipped}  Errors: {errors}")


def main():
    parser = argparse.ArgumentParser(
        description="Synthesize Claude Code session transcripts into vault digests"
    )
    parser.add_argument(
        "--vault",
        default=os.path.expanduser("~/ashco-vault"),
        help="Path to the vault root (default: ~/ashco-vault)",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("VAULT_DEVICE_ID", "default"),
        help="Device identifier for session grouping (default: VAULT_DEVICE_ID env or 'default')",
    )
    args = parser.parse_args()
    run(args.vault, args.device_id)


if __name__ == "__main__":
    main()
