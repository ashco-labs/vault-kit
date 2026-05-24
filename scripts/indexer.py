#!/usr/bin/env python3
"""vault-kit indexer: walks an Obsidian vault, parses frontmatter, computes
content hashes, embeds via Ollama nomic-embed-text, and upserts into
sqlite-vec + FTS5.

Index lives at ~/.vault-index/<vault-name>.db (outside the vault to avoid
SQLite WAL + cloud sync corruption).

Usage:
    python3 indexer.py <vault-path> [--full] [--db <db-path>]
"""

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import sys
import time
from pathlib import Path

import frontmatter
import requests
import sqlite_vec

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
EMBED_MAX_CHARS = 8192
OLLAMA_URL = "http://localhost:11434/api/embed"

SKIP_DIRS = {".obsidian", ".git", ".vault-config", ".DS_Store", ".trash", ".stversions"}

# Relative path prefix -> source_type mapping (longest prefix first)
SOURCE_TYPE_MAP = [
    ("Capture/reader/", "capture:reader"),
    ("Capture/web/", "capture:web"),
    ("Agent/Knowledge/", "agent:knowledge"),
    ("Agent/Research/", "agent:research"),
    ("Agent/Reports/", "agent:reports"),
    ("Agent/Sessions/", "agent:sessions"),
    ("Agent/Artifacts/", "agent:artifacts"),
    ("Daily/", "daily"),
    ("Projects/", "project"),
    ("Entities/", "entity"),
    ("Synced/", "synced"),
    ("Archive/", "archive"),
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vault_vectors (
    file_path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    embedding BLOB,
    source_type TEXT,
    domain TEXT,
    projects TEXT,
    tags TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS vault_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    query TEXT,
    read_at TEXT NOT NULL,
    session_id TEXT,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    results_count INTEGER,
    top_result_path TEXT,
    top_result_similarity REAL,
    searched_at TEXT NOT NULL,
    session_id TEXT
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Create all tables if they don't exist. Load sqlite-vec extension."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    db.executescript(SCHEMA_SQL)

    # FTS5 table (cannot use IF NOT EXISTS directly, check first)
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "vault_fts" not in tables:
        db.execute(
            """CREATE VIRTUAL TABLE vault_fts USING fts5(
                file_path, title, content, tags,
                tokenize='porter unicode61'
            )"""
        )

    if "vault_vec_index" not in tables:
        db.execute(
            f"""CREATE VIRTUAL TABLE vault_vec_index USING vec0(
                file_path TEXT PRIMARY KEY,
                embedding float[{EMBED_DIM}]
            )"""
        )

    db.commit()
    return db


def drop_all(db: sqlite3.Connection) -> None:
    """Drop all indexer-managed tables for a full rebuild."""
    for table in ("vault_fts", "vault_vec_index", "vault_vectors"):
        try:
            db.execute(f"DROP TABLE IF EXISTS {table}")
        except sqlite3.OperationalError:
            pass
    db.commit()


# ---------------------------------------------------------------------------
# Vault walking
# ---------------------------------------------------------------------------


def walk_vault(vault_path: str):
    """Yield all .md file paths under vault_path, skipping dotfiles/dotdirs
    and known non-content directories."""
    vault = Path(vault_path)
    for root, dirs, files in os.walk(vault):
        # Filter dirs in-place to skip unwanted subtrees
        dirs[:] = [
            d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for fname in files:
            if fname.startswith("."):
                continue
            if not fname.endswith(".md"):
                continue
            yield os.path.join(root, fname)


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------


def derive_source_type(rel_path: str) -> str:
    """Map relative path to a source_type string."""
    # Normalize to forward slashes for matching
    normalized = rel_path.replace(os.sep, "/")
    for prefix, stype in SOURCE_TYPE_MAP:
        if normalized.startswith(prefix):
            return stype
    return "other"


def parse_file(file_path: str, vault_root: str) -> dict:
    """Parse a markdown file, extracting frontmatter and computing a content hash.

    Returns a dict with: rel_path, title, content, tags, domain, projects,
    source_type, content_hash, created_at, updated_at, raw_text.
    """
    abs_path = os.path.abspath(file_path)
    abs_root = os.path.abspath(vault_root)
    rel_path = os.path.relpath(abs_path, abs_root)

    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # Parse frontmatter
    try:
        post = frontmatter.loads(raw)
        meta = dict(post.metadata) if post.metadata else {}
        body = post.content
    except Exception:
        meta = {}
        body = raw

    # Extract fields
    title = meta.get("title") or Path(file_path).stem
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    domain = meta.get("domain", "")
    projects = meta.get("projects", [])
    if isinstance(projects, str):
        projects = [projects]
    created_at = str(meta.get("created", ""))
    updated_at = str(meta.get("updated", ""))

    source_type = derive_source_type(rel_path)

    return {
        "rel_path": rel_path,
        "title": title,
        "content": body,
        "tags": tags,
        "domain": domain,
        "projects": projects,
        "source_type": source_type,
        "content_hash": content_hash,
        "created_at": created_at,
        "updated_at": updated_at,
        "raw_text": raw,
    }


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def embed_text(text: str) -> list:
    """Call Ollama API to embed text. Returns a list of floats (768-dim).
    Raises on connection/API errors.

    nomic-embed-text has an 8192-token context window. Since tokenization
    density varies by content (~1-2 chars/token for markdown), we try the
    full truncated text first, then halve on 400 errors until it fits.
    """
    truncated = text[:EMBED_MAX_CHARS]

    for attempt in range(4):
        resp = requests.post(
            OLLAMA_URL,
            json={"model": EMBED_MODEL, "input": truncated},
            timeout=30,
        )
        if resp.status_code == 400 and "context length" in resp.text:
            # Text too long for the model's token window. Halve it.
            truncated = truncated[: len(truncated) // 2]
            continue
        resp.raise_for_status()
        data = resp.json()

        # Ollama returns {"embeddings": [[...]]} for the /api/embed endpoint
        embeddings = data.get("embeddings")
        if embeddings and len(embeddings) > 0:
            return embeddings[0]

        raise ValueError(f"Unexpected Ollama response shape: {list(data.keys())}")

    # Exhausted retries
    resp.raise_for_status()
    raise ValueError("Could not fit text into model context after 4 truncation attempts")


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def index_file(db: sqlite3.Connection, file_path: str, vault_root: str) -> bool:
    """Full pipeline for a single file. Returns True if the file was indexed
    (new or changed), False if skipped (unchanged)."""
    parsed = parse_file(file_path, vault_root)
    rel_path = parsed["rel_path"]

    # Check if content is unchanged
    row = db.execute(
        "SELECT content_hash FROM vault_vectors WHERE file_path = ?",
        (rel_path,),
    ).fetchone()

    if row and row[0] == parsed["content_hash"]:
        return False  # unchanged, skip

    # Embed
    embed_input = f"{parsed['title']}\n{parsed['content']}"
    embedding = embed_text(embed_input)

    # Pack embedding as bytes for vec0
    embedding_bytes = struct.pack(f"{EMBED_DIM}f", *embedding)

    # Upsert vault_vectors
    db.execute(
        """INSERT OR REPLACE INTO vault_vectors
           (file_path, content_hash, embedding, source_type, domain,
            projects, tags, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rel_path,
            parsed["content_hash"],
            embedding_bytes,
            parsed["source_type"],
            parsed["domain"],
            json.dumps(parsed["projects"]),
            json.dumps(parsed["tags"]),
            parsed["created_at"],
            parsed["updated_at"],
        ),
    )

    # Upsert vault_vec_index (vec0 doesn't support REPLACE, so delete first)
    db.execute(
        "DELETE FROM vault_vec_index WHERE file_path = ?", (rel_path,)
    )
    db.execute(
        "INSERT INTO vault_vec_index (file_path, embedding) VALUES (?, ?)",
        (rel_path, embedding_bytes),
    )

    # Upsert vault_fts (delete + insert)
    db.execute("DELETE FROM vault_fts WHERE file_path = ?", (rel_path,))
    tags_str = " ".join(parsed["tags"]) if parsed["tags"] else ""
    db.execute(
        "INSERT INTO vault_fts (file_path, title, content, tags) VALUES (?, ?, ?, ?)",
        (rel_path, parsed["title"], parsed["content"], tags_str),
    )

    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_index(vault_path: str, db_path: str, full: bool = False) -> None:
    """Walk the vault, index every file, clean up stale entries."""
    vault_path = os.path.abspath(vault_path)
    vault_name = os.path.basename(vault_path)

    if not os.path.isdir(vault_path):
        print(f"Error: vault path does not exist: {vault_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Vault:    {vault_path}")
    print(f"DB:       {db_path}")
    print(f"Mode:     {'full rebuild' if full else 'incremental'}")
    print()

    db = init_db(db_path)

    if full:
        print("Dropping existing tables for full rebuild...")
        drop_all(db)
        # Re-init after drop
        db.close()
        db = init_db(db_path)

    # Collect all files first for progress reporting
    print("Scanning vault...", end=" ", flush=True)
    all_files = list(walk_vault(vault_path))
    total = len(all_files)
    print(f"{total} files found.")
    print()

    start_time = time.time()
    indexed = 0
    skipped = 0
    errors = 0
    seen_paths = set()

    for i, fpath in enumerate(all_files):
        rel_path = os.path.relpath(fpath, vault_path)
        seen_paths.add(rel_path)

        try:
            was_indexed = index_file(db, fpath, vault_path)
            if was_indexed:
                indexed += 1
            else:
                skipped += 1
        except requests.exceptions.ConnectionError:
            print(
                f"\n  [error] Ollama not reachable, skipping: {rel_path}",
                file=sys.stderr,
            )
            errors += 1
        except requests.exceptions.Timeout:
            print(
                f"\n  [error] Ollama timeout, skipping: {rel_path}",
                file=sys.stderr,
            )
            errors += 1
        except Exception as e:
            print(
                f"\n  [error] {rel_path}: {e}",
                file=sys.stderr,
            )
            errors += 1

        # Progress every 100 files
        processed = i + 1
        if processed % 100 == 0:
            print(f"  Indexed {processed} / {total}...")

        # Commit every 50 files to avoid holding a huge transaction
        if processed % 50 == 0:
            db.commit()

    db.commit()

    # Clean up stale entries (files that no longer exist on disk)
    deleted = 0
    existing_paths = {
        row[0]
        for row in db.execute("SELECT file_path FROM vault_vectors").fetchall()
    }
    stale = existing_paths - seen_paths
    for stale_path in stale:
        db.execute("DELETE FROM vault_vectors WHERE file_path = ?", (stale_path,))
        db.execute("DELETE FROM vault_fts WHERE file_path = ?", (stale_path,))
        db.execute(
            "DELETE FROM vault_vec_index WHERE file_path = ?", (stale_path,)
        )
        deleted += 1

    if deleted:
        db.commit()

    elapsed = time.time() - start_time

    # Summary
    print()
    print("=" * 50)
    print(f"  Total files:   {total}")
    print(f"  Indexed:       {indexed}")
    print(f"  Skipped:       {skipped} (unchanged)")
    print(f"  Errors:        {errors}")
    print(f"  Deleted:       {deleted} (stale)")
    print(f"  Time:          {elapsed:.1f}s")
    print("=" * 50)

    db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Index an Obsidian vault into sqlite-vec + FTS5"
    )
    parser.add_argument("vault_path", help="Path to the vault root directory")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full rebuild (drop and recreate all tables)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Override default DB path (~/.vault-index/<vault-name>.db)",
    )

    args = parser.parse_args()

    vault_path = os.path.abspath(args.vault_path)
    vault_name = os.path.basename(vault_path)

    if args.db:
        db_path = os.path.abspath(args.db)
    else:
        db_path = os.path.join(
            os.path.expanduser("~"), ".vault-index", f"{vault_name}.db"
        )

    run_index(vault_path, db_path, full=args.full)


if __name__ == "__main__":
    main()
