#!/usr/bin/env python3
"""vault-kit search: hybrid search combining FTS5 BM25 and sqlite-vec cosine
similarity with Reciprocal Rank Fusion (RRF).

Queries the index built by indexer.py at ~/.vault-index/<vault-name>.db.

Usage:
    python3 search.py <query> [--vault <path>] [--top-k N] [--filter key=value] [--db <path>]
"""

import argparse
import json
import os
import re
import sqlite3
import struct
import sys
import time
from pathlib import Path

import requests
import sqlite_vec

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
OLLAMA_URL = "http://localhost:11434/api/embed"

# RRF fusion constant (Cormack et al. 2009)
RRF_K = 60

# BM25 field weights: file_path=0, title=10, content=1, tags=5
BM25_WEIGHTS = (0, 10, 1, 5)

PREVIEW_CHARS = 200

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def open_db(db_path: str) -> sqlite3.Connection:
    """Open the vault index DB and load sqlite-vec."""
    if not os.path.exists(db_path):
        print(f"Error: database not found at {db_path}", file=sys.stderr)
        print("Run indexer.py first to build the index.", file=sys.stderr)
        sys.exit(1)

    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def embed_query(text: str) -> list[float]:
    """Call Ollama to embed a query string. Returns 768-dim float list."""
    resp = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    embeddings = data.get("embeddings")
    if embeddings and len(embeddings) > 0:
        return embeddings[0]

    raise ValueError(f"Unexpected Ollama response shape: {list(data.keys())}")


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def sanitize_fts_query(query: str) -> str:
    """Sanitize a user query for FTS5 MATCH.

    FTS5 interprets certain characters as operators (AND, OR, NOT, NEAR, quotes,
    parens, *, ^, :). Strip them so a plain-language query works as an implicit
    AND of terms.
    """
    # Remove FTS5 operator characters
    cleaned = re.sub(r'[":*^(){}]', " ", query)
    # Collapse whitespace
    cleaned = " ".join(cleaned.split())
    # Escape any remaining bare operators by quoting individual words
    # that happen to be FTS5 keywords
    fts_keywords = {"AND", "OR", "NOT", "NEAR"}
    tokens = []
    for word in cleaned.split():
        if word.upper() in fts_keywords:
            tokens.append(f'"{word}"')
        else:
            tokens.append(word)
    return " ".join(tokens)


def fts_search(
    db: sqlite3.Connection, query: str, top_k: int
) -> list[tuple[str, float]]:
    """FTS5 BM25 search with weighted columns.

    Returns list of (file_path, bm25_score) ordered by relevance.
    BM25 scores are negative; more negative = better match.
    """
    sanitized = sanitize_fts_query(query)
    if not sanitized.strip():
        return []

    try:
        rows = db.execute(
            """SELECT file_path, bm25(vault_fts, ?, ?, ?, ?) AS score
               FROM vault_fts
               WHERE vault_fts MATCH ?
               ORDER BY score
               LIMIT ?""",
            (*BM25_WEIGHTS, sanitized, top_k),
        ).fetchall()
    except sqlite3.OperationalError as e:
        # FTS5 match failure (bad syntax, etc.) -- return empty
        print(f"  [warn] FTS5 query failed: {e}", file=sys.stderr)
        return []

    return [(row[0], row[1]) for row in rows]


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------


def vector_search(
    db: sqlite3.Connection,
    query_embedding: list[float],
    top_k: int,
    filters: dict | None = None,
) -> list[tuple[str, float]]:
    """sqlite-vec KNN search.

    Returns list of (file_path, cosine_similarity) ordered by similarity desc.
    Filters are applied post-fetch by over-fetching from vec0 and joining with
    vault_vectors metadata.
    """
    # Over-fetch when filters are present so post-filtering still yields enough
    fetch_k = top_k * 3 if filters else top_k

    embedding_bytes = struct.pack(f"{EMBED_DIM}f", *query_embedding)

    rows = db.execute(
        """SELECT file_path, distance
           FROM vault_vec_index
           WHERE embedding MATCH ?
             AND k = ?
           ORDER BY distance""",
        (embedding_bytes, fetch_k),
    ).fetchall()

    results = [(row[0], 1.0 - row[1]) for row in rows]  # distance -> similarity

    if not filters:
        return results

    # Apply metadata filters by looking up vault_vectors
    filtered = []
    for file_path, similarity in results:
        meta = db.execute(
            """SELECT source_type, domain, projects, tags, created_at
               FROM vault_vectors WHERE file_path = ?""",
            (file_path,),
        ).fetchone()

        if not meta:
            continue

        source_type, domain, projects_json, tags_json, created_at = meta

        if "source_type" in filters and filters["source_type"] != source_type:
            continue
        if "domain" in filters and filters["domain"] != domain:
            continue
        if "project" in filters:
            projects = json.loads(projects_json) if projects_json else []
            if filters["project"] not in projects:
                continue
        if "created_after" in filters:
            if not created_at or created_at < filters["created_after"]:
                continue
        if "path_prefix" in filters:
            if not file_path.startswith(filters["path_prefix"]):
                continue

        filtered.append((file_path, similarity))

        if len(filtered) >= top_k:
            break

    return filtered


# ---------------------------------------------------------------------------
# RRF merge
# ---------------------------------------------------------------------------


def rrf_merge(
    fts_results: list[tuple[str, float]],
    vec_results: list[tuple[str, float]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion.

    Each result set is ranked 1..N by position. For each file_path appearing
    in either set, the RRF score is the sum of 1/(k + rank) across both sets.

    Returns list of (file_path, rrf_score) sorted descending by score.
    """
    scores: dict[str, float] = {}

    for rank_idx, (file_path, _) in enumerate(fts_results):
        rank = rank_idx + 1  # 1-based
        scores[file_path] = scores.get(file_path, 0.0) + 1.0 / (k + rank)

    for rank_idx, (file_path, _) in enumerate(vec_results):
        rank = rank_idx + 1
        scores[file_path] = scores.get(file_path, 0.0) + 1.0 / (k + rank)

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return merged


# ---------------------------------------------------------------------------
# Result enrichment
# ---------------------------------------------------------------------------


def has_highlights(content: str) -> bool:
    """Check if file content contains a Highlights section with actual content."""
    match = re.search(r"^## Highlights\s*$", content, re.MULTILINE)
    if not match:
        return False
    # Check if there's non-whitespace content after the heading
    after = content[match.end() :]
    # Look for content before the next heading or end of file
    next_heading = re.search(r"^## ", after, re.MULTILINE)
    section = after[: next_heading.start()] if next_heading else after
    return bool(section.strip())


def read_preview(vault_root: str, rel_path: str) -> str:
    """Read the first N chars of the file body (after frontmatter)."""
    abs_path = os.path.join(vault_root, rel_path)
    if not os.path.exists(abs_path):
        return "(file not found on disk)"

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read(4096)  # read enough to get past frontmatter
    except OSError:
        return "(read error)"

    # Strip frontmatter
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            body = raw[end + 3 :].lstrip("\n")
        else:
            body = raw
    else:
        body = raw

    preview = body[:PREVIEW_CHARS].strip()
    if len(body) > PREVIEW_CHARS:
        preview += "..."
    return preview


def enrich_results(
    db: sqlite3.Connection,
    merged: list[tuple[str, float]],
    vec_lookup: dict[str, float],
    vault_root: str,
    top_k: int,
) -> list[dict]:
    """Look up metadata and build final result dicts."""
    results = []

    for file_path, rrf_score in merged[:top_k]:
        # Metadata from vault_vectors
        meta = db.execute(
            """SELECT source_type, domain, projects, tags
               FROM vault_vectors WHERE file_path = ?""",
            (file_path,),
        ).fetchone()

        source_type = meta[0] if meta else ""
        tags = json.loads(meta[3]) if meta and meta[3] else []

        # Title from FTS
        fts_row = db.execute(
            "SELECT title FROM vault_fts WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        title = fts_row[0] if fts_row else Path(file_path).stem

        # Preview + highlights from disk
        preview = read_preview(vault_root, file_path)

        abs_path = os.path.join(vault_root, file_path)
        file_has_highlights = False
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                file_has_highlights = has_highlights(content)
            except OSError:
                pass

        similarity = vec_lookup.get(file_path)

        results.append(
            {
                "file_path": file_path,
                "title": title,
                "preview": preview,
                "similarity": round(similarity, 4) if similarity is not None else None,
                "rrf_score": round(rrf_score, 6),
                "source_type": source_type,
                "has_highlights": file_has_highlights,
                "tags": tags,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Main search
# ---------------------------------------------------------------------------


def hybrid_search(
    db_path: str,
    query: str,
    vault_root: str,
    top_k: int = 15,
    filters: dict | None = None,
) -> list[dict]:
    """Main entry point for hybrid search.

    1. Embed query via Ollama
    2. Run FTS5 search (top_k * 3 candidates)
    3. Run vector search (top_k * 3 candidates, with filters)
    4. Merge with RRF
    5. Enrich top_k results with metadata and previews
    """
    db = open_db(db_path)

    t0 = time.time()

    # Embed
    query_embedding = embed_query(query)
    t_embed = time.time() - t0

    # FTS5
    candidate_k = top_k * 3
    fts_results = fts_search(db, query, candidate_k)
    t_fts = time.time() - t0

    # Vector
    vec_results = vector_search(db, query_embedding, candidate_k, filters)
    t_vec = time.time() - t0

    # Build a lookup for vector similarities
    vec_lookup = {fp: sim for fp, sim in vec_results}

    # RRF merge
    merged = rrf_merge(fts_results, vec_results)
    t_rrf = time.time() - t0

    # Apply path_prefix filter to merged results if present
    # (FTS results don't go through vector_search's filter path)
    if filters:
        filtered_merged = []
        for file_path, score in merged:
            if "path_prefix" in filters and not file_path.startswith(
                filters["path_prefix"]
            ):
                continue
            if "source_type" in filters or "domain" in filters or "project" in filters or "created_after" in filters:
                meta = db.execute(
                    """SELECT source_type, domain, projects, tags, created_at
                       FROM vault_vectors WHERE file_path = ?""",
                    (file_path,),
                ).fetchone()
                if not meta:
                    continue
                source_type, domain, projects_json, tags_json, created_at = meta
                if "source_type" in filters and filters["source_type"] != source_type:
                    continue
                if "domain" in filters and filters["domain"] != domain:
                    continue
                if "project" in filters:
                    projects = json.loads(projects_json) if projects_json else []
                    if filters["project"] not in projects:
                        continue
                if "created_after" in filters:
                    if not created_at or created_at < filters["created_after"]:
                        continue
            filtered_merged.append((file_path, score))
        merged = filtered_merged

    # Enrich
    results = enrich_results(db, merged, vec_lookup, vault_root, top_k)
    t_total = time.time() - t0

    db.close()

    # Attach timing info to the last result as metadata
    timing = {
        "embed_ms": round(t_embed * 1000),
        "fts_ms": round((t_fts - t_embed) * 1000),
        "vec_ms": round((t_vec - t_fts) * 1000),
        "rrf_ms": round((t_rrf - t_vec) * 1000),
        "total_ms": round(t_total * 1000),
        "fts_candidates": len(fts_results),
        "vec_candidates": len(vec_results),
    }

    return results, timing


# ---------------------------------------------------------------------------
# CLI output
# ---------------------------------------------------------------------------


def format_results(results: list[dict], timing: dict) -> str:
    """Format search results for terminal display."""
    lines = []

    if not results:
        lines.append("No results found.")
        lines.append("")
        lines.append(f"  (search took {timing['total_ms']}ms)")
        return "\n".join(lines)

    for i, r in enumerate(results, 1):
        sim_str = f"{r['similarity']:.4f}" if r["similarity"] is not None else "n/a"
        tags_str = ", ".join(r["tags"][:5]) if r["tags"] else "none"
        hl_marker = " [highlights]" if r["has_highlights"] else ""

        lines.append(f"  {i}. {r['title']}")
        lines.append(f"     path: {r['file_path']}")
        lines.append(f"     type: {r['source_type']}  similarity: {sim_str}{hl_marker}")
        lines.append(f"     tags: {tags_str}")
        lines.append(f"     {r['preview']}")
        lines.append("")

    lines.append(
        f"  [{timing['total_ms']}ms total: embed {timing['embed_ms']}ms, "
        f"fts {timing['fts_ms']}ms ({timing['fts_candidates']} hits), "
        f"vec {timing['vec_ms']}ms ({timing['vec_candidates']} hits), "
        f"rrf {timing['rrf_ms']}ms]"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_filters(filter_args: list[str] | None) -> dict | None:
    """Parse --filter key=value arguments into a dict."""
    if not filter_args:
        return None

    filters = {}
    valid_keys = {"source_type", "domain", "project", "created_after", "path_prefix"}

    for filt in filter_args:
        if "=" not in filt:
            print(f"Error: filter must be key=value, got: {filt}", file=sys.stderr)
            sys.exit(1)
        key, value = filt.split("=", 1)
        if key not in valid_keys:
            print(
                f"Error: unknown filter key '{key}'. "
                f"Valid keys: {', '.join(sorted(valid_keys))}",
                file=sys.stderr,
            )
            sys.exit(1)
        filters[key] = value

    return filters if filters else None


def main():
    parser = argparse.ArgumentParser(
        description="Hybrid search over a vault-kit index (FTS5 + sqlite-vec + RRF)"
    )
    parser.add_argument("query", help="Search query string")
    parser.add_argument(
        "--vault",
        default=os.path.expanduser("~/ashco-vault"),
        help="Path to vault root (default: ~/ashco-vault)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=15,
        help="Number of results to return (default: 15)",
    )
    parser.add_argument(
        "--filter",
        action="append",
        dest="filters",
        metavar="key=value",
        help="Metadata filter (repeatable). Keys: source_type, domain, project, created_after, path_prefix",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Override DB path (default: ~/.vault-index/<vault-dir-name>.db)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    vault_root = os.path.abspath(args.vault)
    vault_name = os.path.basename(vault_root)

    if args.db:
        db_path = os.path.abspath(args.db)
    else:
        db_path = os.path.join(
            os.path.expanduser("~"), ".vault-index", f"{vault_name}.db"
        )

    filters = parse_filters(args.filters)

    results, timing = hybrid_search(db_path, args.query, vault_root, args.top_k, filters)

    if args.json_output:
        output = {"results": results, "timing": timing}
        print(json.dumps(output, indent=2))
    else:
        print()
        print(format_results(results, timing))
        print()


if __name__ == "__main__":
    main()
