# Capture Protocol

How an agent decides what to keep from a session and how to write it to the vault.

The core question at session end: what actually matters? Most observations don't survive contact with that question. This protocol makes the evaluation explicit so agents apply it consistently.

---

## The Four Categories

At session end, classify each finding or observation into one category. Findings that don't clearly belong to ACT NOW or RESEARCH usually belong to PARK or KILL.

### ACT NOW

The finding is immediately actionable. Concrete next steps are clear. Someone following up tomorrow would know exactly what to do.

Write to `Agent/Knowledge/<device-id>/` as atomic notes. Include:
- The finding itself (what's true)
- The action (what to do next)
- Provenance (where it came from)

**Examples:**
- "The monarch-mcp server crashes on 401 without retrying. Fix: add a retry with token refresh before re-raising."
- "The FTS5 index is missing the `tags` column. Next step: run `scripts/reindex.sh --rebuild`."
- "The Supabase RLS policy blocks the anon key from reading `captures`. Decision needed: widen or add service-role bypass."

### RESEARCH

Worth remembering as reference, but not immediately actionable. A future agent or human session on this topic would benefit from this note existing.

Write to `Agent/Knowledge/<device-id>/` as atomic notes (if concise) or to `Agent/Research/<device-id>/` as a research report (if this was a bounded investigation).

**Examples:**
- "SQLite FTS5 BM25 scores are negative by convention; lower (more negative) is better."
- "Ollama's `/api/embed` endpoint returns one embedding per input, not batched. Use `/api/embed` with a single string, not a list."
- "The Obsidian Dataview plugin does not support aggregates (SUM, AVG). Use DataviewJS for computed rollups."

### PARK

Might be useful if this topic comes up again, but not worth the note overhead now. The observation isn't wrong; it's just not worth persisting yet.

Don't write to the vault. Let it die with the transcript. If the topic recurs in a future session, the agent can reconstruct or look it up fresh.

**Examples:**
- Tangential details about a library the project isn't using.
- An alternative approach considered and rejected quickly without deep evaluation.
- A version number or changelog detail that's easily re-fetched.

### KILL

Wrong, irrelevant, or superseded during this session. Not worth parking.

Don't write to the vault. A killed observation that was previously in the vault should have its note marked with `superseded_by` pointing to a correction.

**Examples:**
- "Thought FTS5 didn't support `MATCH`, but it does via the virtual table interface." (Kill the misconception; capture the correct understanding under RESEARCH or ACT NOW.)
- An assumption that was disproved before the session ended.
- An observation that turned out to apply to a different project entirely.

---

## Session-End Flow

Run this at the end of every agent session. Sequence matters: capture notes before writing the summary, write the summary after notes exist to link.

```
1. Walk through the session findings. Classify each: ACT NOW / RESEARCH / PARK / KILL.

2. ACT NOW items:
   - Write one atomic note per finding to Agent/Knowledge/<device-id>/
   - Include: what's true, what to do, where it came from
   - Frontmatter: type: atomic, source: agent:<id>, confidence: high|medium|low

3. RESEARCH items:
   - Concise finding: atomic note in Agent/Knowledge/<device-id>/
   - Bounded investigation: research report in Agent/Research/<device-id>/
   - Research report frontmatter: topic, sources_consulted, as_of

4. Research reports written mid-session:
   - Already exist in Agent/Research/<device-id>/
   - Verify frontmatter is complete; update as_of if revised

5. Write session summary to Agent/Chats/<device-id>/:
   - Use session-summary-template.md
   - Link all atomic notes and research reports created this session
   - Record open threads (unresolved, handed off, or deferred)

6. Update Agent/hot.md:
   - Remove items resolved this session
   - Add new cross-session threads or blockers
   - Keep it under 50 lines

7. Git commit:
   git add -A
   git commit --author="Claude Agent <agent@local>" -m "agent: session $(date +%Y-%m-%d) <slug>"

8. PARK and KILL items: no vault writes. They die with the transcript.
```

---

## Writing Atomic Notes

Structure for an ACT NOW or RESEARCH atomic note:

```markdown
---
title: "SQLite FTS5 BM25 scores are negative"
type: atomic
source: agent:claude-code
tags: [sqlite, fts5, search, bm25, indexing]
created: 2026-05-23
confidence: high
last_agent_update: 2026-05-23
---

FTS5's `bm25()` function returns negative values by convention: more relevant
results have lower (more negative) scores. This is the opposite of most ranking
functions.

When sorting by relevance: `ORDER BY bm25(notes_fts) ASC` (not DESC).

Source: SQLite FTS5 documentation, confirmed via test query on vault index.
```

Keep atomic notes short: 3-10 sentences for the body. If you need more, it's probably a research report.

---

## Writing Research Reports

For bounded investigations where the output is a reference document, not a single finding:

```markdown
---
title: "sqlite-vec cosine similarity performance at 10K vectors"
type: research
source: agent:claude-code
tags: [sqlite, sqlite-vec, performance, embeddings, search]
created: 2026-05-23
topic: "How sqlite-vec scales cosine similarity queries at 10K+ vectors without an ANN index"
sources_consulted: ["sqlite-vec README", "[[sqlite-vec-setup]]", "benchmark script output"]
as_of: 2026-05-23
confidence: medium
last_agent_update: 2026-05-23
---

## Question

Does sqlite-vec support approximate nearest neighbor (ANN) search, or is it
always exact? What's the performance floor at 10K vectors?

## Findings

- sqlite-vec 0.1.x is exact-only (no ANN / HNSW index).
- At 10K 768-dim vectors, a cosine scan takes ~80ms on an M4 Mini.
- At 50K vectors, ~400ms. Acceptable for interactive search; not for batch.
- A planned HNSW index is on the sqlite-vec roadmap but not in 0.1.x.

## Recommendation

Use exact search for vaults under 30K notes. For larger vaults, pre-filter
by FTS5 (top 500 BM25 candidates) before running the vector scan.

## Open Questions

- Does sqlite-vec handle int8 quantization? (Not checked.)
```

---

## hot.md

`Agent/hot.md` is a single-writer cross-session state file. It is not a task list and not a journal. It holds only threads that need to survive to the next session.

Keep it under 50 lines. One bullet per thread:

```markdown
# Hot Threads

- [ ] ASH-212: vault-kit reindex failing on notes with no tags — needs fix in scripts/reindex.sh
- [ ] Decision needed: should Entities/ be agent-writable? (see session 2026-05-22)
- [ ] Research pending: sqlite-vec int8 quantization — didn't finish this session
```

When a thread resolves, delete its line. Don't mark it done and leave it; hot.md is not an audit log. Session summaries are the audit log.
