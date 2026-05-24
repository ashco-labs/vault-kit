# Architecture

vault-kit's design centers on one constraint: agents need to read and write to a personal knowledge base without requiring a cloud service, a special app, or a complex backend. The substrate is an Obsidian vault (plain markdown files) with a local SQLite index. The interface is an MCP stdio server.

---

## User Interaction Model

Three surfaces. Each has a distinct owner and write boundary:

**Capture** (`Capture/`, `Daily/`, `Synced/`) — user-authored or sync-authored content flows in from the outside world. Reader-sync writes to `Capture/reader/`. Meeting summaries land in `Synced/meetings/`. The user edits daily notes in `Daily/`. Agents read these but do not write here.

**Active work** (`Projects/`) — the user creates and manages project directories. Agents contribute notes within a project by writing to `Agent/Knowledge/` with `projects:` frontmatter pointing at the project slug. The project index note in `Projects/<slug>/index.md` is user-owned.

**Agent output** (`Agent/`) — agents write here exclusively: atomic notes, research reports, session summaries, artifacts, and the cross-session state file `Agent/hot.md`. Partitioned by device ID to prevent sync conflicts.

---

## Vault Directory Structure

```
vault-root/
├── .vault-config/          → symlink to vault-kit/protocol/
│
├── Agent/                  [STRICT — agent-owned]
│   ├── hot.md              cross-session state, single file
│   ├── Knowledge/<dev>/    atomic notes by device
│   ├── Research/<dev>/     research reports by device
│   ├── Reports/<dev>/      audit and review reports by device
│   ├── Sessions/<dev>/     session summaries by device
│   └── Artifacts/<dev>/    diagrams and structured outputs by device
│
├── Capture/
│   ├── reader/             [STRICT — reader-sync only]
│   └── web/                user web clippings
│
├── Daily/                  [STRICT — user only]
├── Projects/NNN-name/      [FLEXIBLE — user creates, agents reference]
├── Entities/               [STRICT — user only]
├── Synced/                 [STRICT — sync processes only]
└── Archive/                [FLEXIBLE]
```

**Strict vs Flexible.** Strict directories have enforced write rules: tools either own them exclusively or are blocked from writing. Flexible directories follow conventions but allow user reorganization without breaking vault-kit.

**Per-Device Partitioning.** Each device gets its own subdirectory inside every `Agent/` corpus. `Agent/Knowledge/mac-mini/` and `Agent/Knowledge/laptop/` don't conflict when the vault syncs across machines via iCloud or OneDrive. `Agent/hot.md` is the sole exception: single-writer, last-write-wins on sync conflict.

---

## Search Architecture

### Why Hybrid

Pure vector search (embedding-only) struggles with proper nouns, version numbers, exact function names, and queries where the user knows the exact word they want. Pure keyword search (FTS only) misses paraphrases, conceptual queries, and cases where the user describes what they mean without using the exact vocabulary in the notes.

Hybrid search runs both and fuses the results. For a query like "how do I handle auth errors in the mcp server," vector search finds semantically similar notes while FTS5 catches notes that mention "auth errors" or "mcp" verbatim. The fused result is better than either alone.

### Stack

```
query string
    │
    ├─── FTS5 MATCH ──────► BM25 rank list (top 100)
    │                              │
    └─── Ollama embed ──► cosine scan ──► cosine rank list (top 100)
                                   │
                          RRF fusion (k=60)
                                   │
                          top_k results (default: 15)
```

**FTS5 BM25.** SQLite's built-in full-text search with BM25 scoring. Field weights: title 10x, tags 5x, content 1x. A title match counts as 10 body matches for scoring purposes. Tags encode curated vocabulary, so they're weighted above body text.

**sqlite-vec cosine similarity.** sqlite-vec 0.1.9 as a SQLite loadable extension. Each note's full text is embedded into a 768-dim float32 vector using Ollama (`nomic-embed-text`). Queries are embedded the same way and compared via cosine similarity. No approximate nearest neighbor (ANN) index in v0.1.x: exact scan. At 10K notes, ~80ms on M4 Mini. At 30K notes, ~240ms.

**Reciprocal Rank Fusion (RRF, k=60).** RRF scores each document as the sum of `1/(k+r)` across rank lists, where `r` is the document's rank in each list. k=60 is the standard value from the original paper (Cormack et al., 2009). It doesn't require score normalization between BM25 and cosine, which avoids the scale mismatch problem.

**Filters.** Applied at the SQL layer before ranking, not post-hoc. Available: `source_type`, `domain`, `project`, `created_after`, `path_prefix`. Multiple filters are ANDed. Both FTS5 and vector queries respect the same WHERE clause.

### Index Storage

The index lives at `~/.vault-index/<vault-name>.db`, outside the vault directory. This keeps the vault itself clean for Obsidian, iCloud sync, and git. The index is fully regenerable from vault content: running `scripts/indexer.py --rebuild` drops and recreates it. No data is lost on index deletion.

**Schema (abbreviated):**

```sql
-- Note metadata + FTS content
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE,
    title TEXT,
    type TEXT,
    source TEXT,
    domain TEXT,
    project TEXT,
    tags TEXT,         -- space-separated for FTS
    content TEXT,
    created TEXT,
    last_agent_update TEXT,
    device_id TEXT,
    indexed_at TEXT
);

-- FTS5 virtual table
CREATE VIRTUAL TABLE notes_fts USING fts5(
    title, tags, content,
    content=notes, content_rowid=id
);

-- sqlite-vec embedding table
CREATE VIRTUAL TABLE vec_notes USING vec0(
    embedding FLOAT[768]
);

-- Observability
CREATE TABLE vault_reads   (ts TEXT, path TEXT, source TEXT);
CREATE TABLE vault_searches (ts TEXT, query TEXT, results_count INTEGER, filters TEXT);
```

---

## MCP Server

Three tools over stdio. The server reads from the SQLite index; it writes to the vault filesystem via `capture_knowledge`.

### `search_vault`

Parameters:
- `query` (string): the search query
- `top_k` (integer, default 15): result count
- `filters` (object): `source_type`, `domain`, `project`, `created_after`, `path_prefix`

Returns: array of results with `path`, `title`, `type`, `score`, `snippet`.

Logs to `vault_searches` analytics table.

### `capture_knowledge`

Parameters:
- `title` (string): note title
- `type` (string): `atomic` | `research` | `working-note`
- `content` (string): note body
- `tags` (array): 5-15 tags
- `projects` (array, optional): project slugs
- `domain` (string, optional): domain category
- `confidence` (string, optional): `high` | `medium` | `low`

Writes a markdown file to `Agent/Knowledge/<device-id>/YYYY-MM-DD-<slug>.md` with full frontmatter. Queues for incremental reindex. Returns the path of the created file.

### `vault_stats`

No parameters. Returns:
- Total note count
- Notes by type
- Index last updated
- Device ID
- Vault path

---

## Session Protocol

A structured cadence for what an agent does at session start, mid-session, and session end.

### Session Start

1. Read `Agent/hot.md` (cross-session threads and blockers)
2. Read today's daily note from `Daily/YYYY-MM-DD.md` (user context)
3. If the session has a project context, read `Projects/<slug>/index.md`
4. Run `search_vault` for the session's topic to surface prior knowledge
5. Proceed with the session's work

### Mid-Session

When a research thread produces findings, write them immediately rather than accumulating everything for the end. A note written mid-session has better provenance than one reconstructed from memory at session end.

### Session End (Panning for Gold)

1. Classify each finding: ACT NOW / RESEARCH / PARK / KILL
2. Write ACT NOW findings as atomic notes to `Agent/Knowledge/<device-id>/`
3. Write RESEARCH findings as atomic notes (concise) or research reports (bounded investigations)
4. Write session summary to `Agent/Sessions/<device-id>/YYYY-MM-DD-<slug>.md`
5. Update `Agent/hot.md` (remove resolved threads, add new cross-session threads)
6. Commit: `git commit --author="Claude Agent <agent@local>" -m "agent: session YYYY-MM-DD <slug>"`

---

## Observability

Two analytics tables in the SQLite index:

**`vault_searches`** — every search query, timestamp, result count, and filters. Use for:
- Identifying common query patterns (worth promoting to hot.md or a summary note)
- Finding searches that return 0 results (gaps in the knowledge base)

**`vault_reads`** — every note read via MCP, with path and caller source. Use for:
- Identifying notes that are frequently accessed (promote to hot.md context)
- Confirming that a particular note was actually used in a session

Neither table is replicated or synced. It stays in the local index file.

---

## Git Audit Model

The vault uses local git. No remote push. Three identities:

| Identity | Author | Email | When |
|---|---|---|---|
| User | From `git config` | From `git config` | Manual Obsidian edits |
| Claude Agent | `Claude Agent` | `agent@local` | Agent vault writes |
| Auto-Sweep | `Auto-Sweep` | `sweep@local` | Hourly cron catch-all |

The Auto-Sweep cron commits any uncommitted changes on an hourly schedule. This catches edits made directly in Obsidian that the user didn't explicitly commit, and provides a consistent audit trail without requiring the user to think about git.

For per-note provenance, `last_agent_update` in frontmatter records the last date an agent edited the note. Human edits don't update this field.

---

## Per-Device Partitioning Rationale

When a vault syncs across two machines (iCloud, OneDrive, Syncthing), two agents can run simultaneously. Without partitioning, both would write to the same paths and create sync conflicts.

The solution: each device gets a `<device-id>` subdirectory under every `Agent/` corpus directory. `mac-mini` writes to `Agent/Knowledge/mac-mini/`; `laptop` writes to `Agent/Knowledge/laptop/`. Both subdirectories sync freely. Neither overwrites the other.

`Agent/hot.md` breaks this rule intentionally. It's a single shared state file because its purpose is cross-session, cross-device coordination. Sync conflicts on hot.md are rare (it updates at session boundaries, not mid-session) and low-stakes (keep the newer version).

---

## Data Flow

**Write path (capture):**

```
agent: capture_knowledge(title, content, tags, ...)
    → MCP server validates frontmatter
    → writes .md to Agent/Knowledge/<device-id>/
    → queues path for incremental indexer
    → indexer runs: embeddings via Ollama, FTS5 insert, vec_notes insert
    → returns { path, title }
```

**Read path (search):**

```
agent: search_vault(query, top_k, filters)
    → MCP server: embed query via Ollama
    → SQLite: FTS5 MATCH with BM25 (top 100, filtered)
    → SQLite: vec0 cosine scan (top 100, filtered)
    → RRF fusion → top_k results
    → log to vault_searches
    → return results with path, title, snippet, score
```

**Index rebuild path:**

```
scripts/indexer.py --rebuild
    → walk vault filesystem for .md files
    → parse frontmatter (YAML)
    → embed content via Ollama (batch where possible)
    → rebuild FTS5 content table + vec0 table
    → write indexed_at to each row
```
