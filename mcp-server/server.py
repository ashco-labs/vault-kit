#!/usr/bin/env python3
"""vault-kit MCP server: exposes vault search, knowledge capture, and stats
via the Model Context Protocol (stdio transport).

Environment variables:
  VAULT_PATH       Path to vault root (required, e.g. ~/ashco-vault)
  VAULT_DEVICE_ID  Device identifier for per-device partitioning (default "default")
  VAULT_DB_PATH    Override DB path (optional, default ~/.vault-index/<vault-name>.db)
"""

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import sqlite_vec
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# ---------------------------------------------------------------------------
# Add scripts/ to sys.path so we can import search and indexer
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from search import hybrid_search  # noqa: E402
from indexer import index_file, init_db  # noqa: E402

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

VAULT_PATH = os.environ.get("VAULT_PATH", "")
VAULT_DEVICE_ID = os.environ.get("VAULT_DEVICE_ID", "default")
VAULT_DB_PATH = os.environ.get("VAULT_DB_PATH", "")


def resolve_paths() -> tuple[str, str]:
    """Resolve vault root and DB path from env vars. Raises on missing VAULT_PATH."""
    if not VAULT_PATH:
        raise RuntimeError("VAULT_PATH environment variable is required")

    vault_root = os.path.realpath(os.path.expanduser(VAULT_PATH))
    if not os.path.isdir(vault_root):
        raise RuntimeError(f"VAULT_PATH does not exist: {vault_root}")

    if VAULT_DB_PATH:
        db_path = os.path.realpath(os.path.expanduser(VAULT_DB_PATH))
    else:
        vault_name = os.path.basename(vault_root)
        db_path = os.path.join(
            os.path.expanduser("~"), ".vault-index", f"{vault_name}.db"
        )

    return vault_root, db_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def open_db(db_path: str) -> sqlite3.Connection:
    """Open the vault index DB with sqlite-vec loaded. WAL mode + 30s busy timeout
    for concurrent access from indexer-watch, cron, and MCP server."""
    db = sqlite3.connect(db_path, timeout=30)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    return db


def slugify(text: str, max_len: int = 50) -> str:
    """Lowercase, replace non-alphanum with hyphens, collapse, trim."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len].rstrip("-")


def log_search(db_path: str, query: str, results: list[dict]) -> None:
    """Log a search query to vault_searches table."""
    db = open_db(db_path)
    try:
        top_path = results[0]["file_path"] if results else None
        top_sim = results[0].get("similarity") if results else None
        db.execute(
            """INSERT INTO vault_searches
               (query, results_count, top_result_path, top_result_similarity, searched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (query, len(results), top_path, top_sim,
             datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    finally:
        db.close()


def log_reads(db_path: str, query: str, file_paths: list[str]) -> None:
    """Log each result file to vault_reads table."""
    db = open_db(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        for fp in file_paths:
            db.execute(
                """INSERT INTO vault_reads
                   (file_path, query, read_at, source)
                   VALUES (?, ?, ?, ?)""",
                (fp, query, now, "search_result"),
            )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tool implementations (sync, run via asyncio.to_thread)
# ---------------------------------------------------------------------------


def do_search_vault(
    query: str,
    top_k: int = 15,
    filters: dict | None = None,
) -> dict:
    """Execute hybrid search, log results, return structured response."""
    vault_root, db_path = resolve_paths()

    results, timing = hybrid_search(db_path, query, vault_root, top_k, filters)

    # Log the search and reads
    log_search(db_path, query, results)
    result_paths = [r["file_path"] for r in results]
    if result_paths:
        log_reads(db_path, query, result_paths)

    # Strip rrf_score from results (internal detail)
    clean_results = []
    for r in results:
        clean_results.append({
            "file_path": r["file_path"],
            "title": r["title"],
            "preview": r["preview"],
            "similarity": r.get("similarity"),
            "source_type": r.get("source_type", ""),
            "has_highlights": r.get("has_highlights", False),
            "tags": r.get("tags", []),
        })

    return {
        "results": clean_results,
        "query": query,
        "total": len(clean_results),
        "timing_ms": timing.get("total_ms", 0),
    }


def do_capture_knowledge(
    content: str,
    title: str,
    note_type: str = "atomic",
    projects: list[str] | None = None,
    domain: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Create a knowledge note in the vault, index it, and git commit."""
    vault_root, db_path = resolve_paths()
    device_id = VAULT_DEVICE_ID

    today = date.today().isoformat()
    slug = slugify(title)

    # Build frontmatter + body first so we can hash the full file content
    fm_lines = [
        "---",
        f"title: {title}",
        f"type: {note_type}",
        "source: agent:claude-code",
    ]
    if projects:
        fm_lines.append(f"projects: {json.dumps(projects)}")
    if domain:
        fm_lines.append(f"domain: {domain}")
    if tags:
        fm_lines.append(f"tags: {json.dumps(tags)}")
    else:
        fm_lines.append("tags: []")
    fm_lines.append(f"created: {today}")
    fm_lines.append(f"last_agent_update: {today}")
    fm_lines.append("---")

    file_content = "\n".join(fm_lines) + "\n\n" + content + "\n"

    # Hash the full file content (matches what the indexer stores)
    content_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()
    short_hash = content_hash[:6]

    # Dedup check against indexed hashes
    db = open_db(db_path)
    try:
        existing = db.execute(
            "SELECT file_path FROM vault_vectors WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
    finally:
        db.close()

    if existing:
        return {
            "file_path": existing[0],
            "title": title,
            "tags": tags or [],
            "deduplicated": True,
            "message": f"Content already exists at {existing[0]}",
        }

    # Generate filename and write
    filename = f"{today}-{slug}-{short_hash}.md"
    knowledge_dir = os.path.join(vault_root, "Agent", "Knowledge", device_id)
    os.makedirs(knowledge_dir, exist_ok=True)
    abs_path = os.path.join(knowledge_dir, filename)
    rel_path = os.path.relpath(abs_path, vault_root)

    # Write file
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(file_content)

    # Index immediately
    db = init_db(db_path)
    try:
        index_file(db, abs_path, vault_root)
        db.commit()
    finally:
        db.close()

    # Git commit
    try:
        subprocess.run(
            ["git", "-C", vault_root, "add", rel_path],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            [
                "git", "-C", vault_root, "commit",
                "--author=Claude Agent <agent@local>",
                "-m", f"feat(knowledge): {title}",
            ],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # git not available or timed out; file still written + indexed

    return {
        "file_path": rel_path,
        "title": title,
        "tags": tags or [],
        "deduplicated": False,
    }


def do_vault_stats() -> dict:
    """Gather aggregate stats from the vault index."""
    _, db_path = resolve_paths()
    db = open_db(db_path)

    try:
        # Files by source_type
        rows = db.execute(
            """SELECT source_type, COUNT(*) as cnt
               FROM vault_vectors
               GROUP BY source_type
               ORDER BY cnt DESC"""
        ).fetchall()
        by_source_type = {row[0]: row[1] for row in rows}

        # Total files in FTS
        fts_total = db.execute(
            "SELECT COUNT(*) FROM vault_fts"
        ).fetchone()[0]

        # Index freshness (most recent updated_at)
        freshness_row = db.execute(
            "SELECT MAX(updated_at) FROM vault_vectors"
        ).fetchone()
        index_freshness = freshness_row[0] if freshness_row and freshness_row[0] else None

        # Files never read
        never_read = db.execute(
            """SELECT COUNT(*)
               FROM vault_vectors v
               LEFT JOIN vault_reads r ON v.file_path = r.file_path
               WHERE r.file_path IS NULL"""
        ).fetchone()[0]

        # Top 10 search queries
        top_queries_rows = db.execute(
            """SELECT query, COUNT(*) as cnt
               FROM vault_searches
               GROUP BY query
               ORDER BY cnt DESC
               LIMIT 10"""
        ).fetchall()
        top_queries = [{"query": row[0], "count": row[1]} for row in top_queries_rows]

        # Total vectors
        total_vectors = db.execute(
            "SELECT COUNT(*) FROM vault_vectors"
        ).fetchone()[0]

    finally:
        db.close()

    return {
        "total_files_indexed": total_vectors,
        "total_fts_entries": fts_total,
        "files_by_source_type": by_source_type,
        "index_freshness": index_freshness,
        "files_never_read": never_read,
        "top_search_queries": top_queries,
    }


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("vault-kit")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_vault",
            description=(
                "Search the vault for prior knowledge using hybrid vector + "
                "full-text search with Reciprocal Rank Fusion. Returns ranked "
                "results with title, preview, similarity score, and metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 15)",
                        "default": 15,
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional filters: source_type, domain, project, created_after (YYYY-MM-DD), path_prefix",
                        "properties": {
                            "source_type": {"type": "string"},
                            "domain": {"type": "string"},
                            "project": {"type": "string"},
                            "created_after": {"type": "string"},
                            "path_prefix": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="capture_knowledge",
            description=(
                "Capture a new knowledge note into the vault. Writes a "
                "markdown file with frontmatter to Agent/Knowledge/<device>/, "
                "indexes it immediately, and git commits. Deduplicates by "
                "content hash."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The note content (markdown body)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Note title",
                    },
                    "type": {
                        "type": "string",
                        "description": "Note type (default 'atomic')",
                        "default": "atomic",
                    },
                    "projects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Project slugs this note belongs to",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Domain category",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the note",
                    },
                },
                "required": ["content", "title"],
            },
        ),
        types.Tool(
            name="vault_stats",
            description=(
                "Get aggregate statistics about the vault index: file counts "
                "by source type, index freshness, unread file count, and top "
                "search queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "search_vault":
            result = await asyncio.to_thread(
                do_search_vault,
                query=arguments["query"],
                top_k=arguments.get("top_k", 15),
                filters=arguments.get("filters"),
            )
        elif name == "capture_knowledge":
            result = await asyncio.to_thread(
                do_capture_knowledge,
                content=arguments["content"],
                title=arguments["title"],
                note_type=arguments.get("type", "atomic"),
                projects=arguments.get("projects"),
                domain=arguments.get("domain"),
                tags=arguments.get("tags"),
            )
        elif name == "vault_stats":
            result = await asyncio.to_thread(do_vault_stats)
        else:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"}),
            )]

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}),
        )]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
