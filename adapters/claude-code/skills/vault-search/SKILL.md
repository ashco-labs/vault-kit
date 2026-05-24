---
name: vault-search
description: Search the vault for prior knowledge using hybrid vector + full-text search
triggers:
  - "search my vault" / "what do I know about" / "find that thing I read about"
  - "what did I save on <topic>" / "find that note about"
  - session start (auto-load hot.md, daily notes, project context before any work)
  - context-needing question where prior research may exist
---

## When to Search

**Session start (automatic).** Before doing any work, load baseline context per the
session start protocol below. This is not optional; it prevents redundant research and
keeps cross-session threads alive.

**Mid-session context needs.** When the user asks a question where prior research is
likely (engineering decisions, domain-specific questions, recurring workflows), search
before answering from training data. Training data is a fallback, not a first resort.

**Explicit user request.** "Search my vault," "what do I know about X," "find that note."
Run `search_vault` with the user's query. Present results ranked by relevance.

---

## Session Start Protocol

Run this sequence before responding to the user's opening message:

1. Read `Agent/hot.md`. This is cross-session state: active threads, blockers, and what
   the last session left open. If this file doesn't exist, the vault is either new or
   the last agent session didn't close cleanly.

2. Read the last 3-5 daily notes (`Daily/YYYY-MM-DD.md`). These give recent context from
   the user's perspective outside agent sessions.

3. Read the last 2-3 session summaries from `Agent/Chats/<device-id>/`. These are
   the searchable receipts of prior agent work, with links to every note created.

4. Detect project from the user's opening message. Watch for `NNN-name` slug patterns
   or partial names matching a directory under `Projects/`. If matched, load
   `Projects/<NNN-name>/index.md` and the active files in that directory (excluding
   `Archive/`).

5. Call `search_vault` with a query derived from the session objective. Use `top_k=15`
   (the default). Narrow with filters if the project slug is known (`project: "NNN-name"`).

Present a brief orientation: what you found in hot.md, count of relevant vault items,
and project state if loaded. Then ask for or proceed with the session.

---

## How to Call search_vault

```
search_vault(
  query: "the user's question or derived objective",
  top_k: 15,           # increase to 25+ for broad exploration queries
  filters: {           # all optional; AND'd if multiple provided
    project: "001-monarch-review",
    domain: "personal-finance",
    path_prefix: "Agent/Knowledge/",
    created_after: "2026-01-01"
  }
)
```

The search combines FTS5 BM25 and sqlite-vec cosine similarity via RRF fusion. Both
keyword and semantic matches surface. See `protocol/search-defaults.md` for parameter
details and performance notes.

---

## Interpreting Results

Results arrive ranked by RRF score (best first). Fields to check:

- `title`: the note's title
- `path`: vault-relative path (indicates note type: Knowledge vs Research vs Capture)
- `source`: who wrote it (`agent:claude-code`, `reader-sync`, `human`)
- `tags`: curated vocabulary; useful for confirming relevance
- `preview` or `snippet`: matched content excerpt

Reader captures (`Capture/reader/`) may have user highlights and annotations. When
they appear in results, note this: "This Reader capture has your highlights." That
signals the user has already engaged with this source.

Research reports (`Agent/Research/`) are bounded investigations from prior sessions.
Check `as_of` in frontmatter; stale reports (3+ months old on fast-moving topics)
should be flagged.

---

## Presenting Results

For an explicit search request, present the top 5-10 results. For each:
- Title and vault path (one line)
- One-sentence preview of the relevant content
- Flag if it has user annotations or is a research report

Format: concise list, not a wall of text. The user can ask to open any specific note.

For session start orientation, summarize the count and highlight anything directly
relevant to the stated objective. Don't list every result; surface the signal.

---

## References

- `protocol/search-defaults.md` — algorithm, parameter rationale, performance notes
- `protocol/vault-structure.md` — directory layout (what paths mean)
- `recipes/project-context-loading.md` — full session start and project detection recipe
