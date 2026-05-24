# hot.md Management

`Agent/hot.md` is a single-writer cross-session state file. It holds only threads that
need to survive to the next session: active work, open decisions, and known blockers.

It is not a task list. It is not a journal. Old content belongs in session summaries.

---

## What hot.md Contains

The file is 50-150 lines, fully overwritten on each update (not appended to).

### Frontmatter

```yaml
---
last_refreshed: 2026-05-23T14:32
refreshed_by: shutdown | manual | chat-synth
tags: [hot, cross-session-state]
---
```

**last_refreshed** — ISO timestamp of the last update, local time. Lets the next session
know how stale the file is.

**refreshed_by** — what triggered the update:
- `shutdown`: Panning for Gold at the end of an agent session (normal path)
- `manual`: the user explicitly asked the agent to update hot.md mid-session
- `chat-synth`: the chat-synth cron updated `Recent sessions` without a full session end

### Sections

**Currently active** — what is being worked on right now or was in progress at the last
session end. Specific enough that a fresh session can pick up without asking. One bullet
per thread.

```markdown
## Currently active

- [ ] ASH-212: vault-kit reindex failing on notes with no tags — fix in `scripts/reindex.sh`
- [ ] Decision pending: should Entities/ be agent-writable? Relevant context: [[2026-05-22-entities-write-discussion]]
```

**Recent sessions** — the last 4-6 session summaries, listed as wikilinks with one-line
descriptions. Gives the next session a quick overview of what has happened recently.

```markdown
## Recent sessions

- [[2026-05-23-hybrid-search-tuning]] — RRF k=60 adopted; FTS5 weights set
- [[2026-05-22-entities-write-policy]] — Deferred decision on agent writes to Entities/
- [[2026-05-21-reindex-fix]] — Fixed sqlite-vec column error; reindex works
```

**Next likely action** — one or two sentences on the most obvious next step. Not a
prediction, just orientation for the next session.

```markdown
## Next likely action

Continue vault-kit search implementation. The sqlite-vec int8 quantization question
is still open — either answer it or park it.
```

**Open threads** — anything that crosses session boundaries and isn't in "Currently active."
Pending decisions, waiting-on-external items, background research in progress.

```markdown
## Open threads

- [ ] Research pending: sqlite-vec int8 quantization — didn't finish last session
- [ ] Waiting: Ashton to review search weight config before shipping
- [ ] Background: should Capture/web/ be agent-readable? No urgency.
```

---

## Write Triggers

**Primary: Panning for Gold at session close.** The agent fully rewrites hot.md as the
last step before the git commit. Remove threads that resolved this session. Add new
threads or blockers that emerged. Update "Recent sessions" with the just-completed
session summary.

**Secondary: Semantic breakpoints mid-session.** If a significant decision is made or a
blocker is discovered mid-session, the agent may rewrite hot.md immediately rather than
waiting for session end. This ensures the state is accurate if the session ends
unexpectedly.

**Tertiary: Manual request.** The user can ask the agent to update hot.md at any point.

**Cron: chat-synth.** A scheduled job may update the "Recent sessions" section when new
session summaries appear, without doing a full rewrite. It sets `refreshed_by: chat-synth`.

---

## Read Triggers

**Automatic at session start** — load hot.md before any other vault reads. It's the
primary cross-session state; everything else is supplemental.

**On demand** — when the user asks "where were we", "what's in flight", or similar. Read
hot.md and summarize the currently active threads and next likely action.

---

## Lifecycle: Fully Overwritten

Each update replaces the entire file. Do not append to hot.md. The complete current
state should be readable from the file alone, without hunting through history.

Old content belongs in session summaries. If a thread resolves, delete its line. If a
thread evolves, rewrite its line with the new state. Don't leave resolved or completed
items in hot.md; they add noise and hide the current state.

Git history preserves every prior version. If you need to see what hot.md said last
week, run:

```bash
git log --follow --oneline -- "Agent/hot.md"
git show <commit-hash>:Agent/hot.md
```

---

## Single-Writer Rule

`Agent/hot.md` is single-writer: only the primary device writes it. Other devices read it.

When the vault is synced across multiple machines (iCloud, OneDrive, Syncthing), the
"primary device" is whichever machine is doing active agent work. If you're running an
agent session, you're the primary writer for that session.

Conflicts are rare because hot.md updates happen at session boundaries. If a sync
conflict occurs, keep the newer version. The `last_refreshed` timestamp tells you
which is newer.

---

## Size Discipline

Keep hot.md between 50 and 150 lines.

If it's growing beyond 150 lines, you're probably:
- Keeping resolved threads (delete them)
- Writing narrative instead of bullets (tighten)
- Including content that belongs in a session summary or atomic note (move it)

If it's under 50 lines and there's active work, you're probably:
- Missing threads that exist but aren't tracked
- Writing too tersely to be useful

The goal is a file that a fresh agent session can read in seconds and understand the
current state of work.

---

## Example hot.md

```markdown
---
last_refreshed: 2026-05-23T16:45
refreshed_by: shutdown
tags: [hot, cross-session-state]
---

## Currently active

- [ ] vault-kit MCP server: implement `capture_knowledge` tool — blocked on sqlite-vec
  schema finalization (see [[vault-kit-schema-v1-decision]])
- [ ] ASH-214: reindex performance at 30K notes — benchmark not run yet

## Recent sessions

- [[2026-05-23-hybrid-search-tuning]] — RRF k=60 adopted; FTS5 title/tags/content weights set
- [[2026-05-22-sqlite-vec-schema]] — Schema decided; migration written; reindex tested at 500 notes
- [[2026-05-21-reindex-bug-fix]] — Fixed missing `embedding BLOB` column in migration
- [[2026-05-20-search-algorithm-design]] — Chose RRF over linear combination; rationale in atomic note

## Next likely action

Finalize `capture_knowledge` MCP tool. Schema is locked; implementation is
straightforward. Then run reindex benchmark at 30K notes.

## Open threads

- [ ] sqlite-vec int8 quantization: worth evaluating for large vaults (>30K notes). Park
  until reindex benchmark reveals whether latency is a problem.
- [ ] Decision: should session summaries include `duration` as estimated or actual?
  Currently we estimate; actual timestamps would require agent platform support.
```

---

## References

- `capture-protocol.md` — full session-end flow, including hot.md update as step 6
- `session-capture.md` — Panning for Gold recipe that drives the primary write trigger
- `vault-structure.md` — single-writer partitioning rule for hot.md
- `audit-model.md` — git identity conventions for the commit that follows the hot.md update
