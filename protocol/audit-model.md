# Audit Model

vault-kit uses a three-identity git model to track who wrote what to the vault.
The vault's git history is local-only. No remote push.

---

## The Three Identities

| Identity | Git Author | Git Email | When Used |
|---|---|---|---|
| User | From git config | From git config | Manual Obsidian edits, direct file changes |
| Claude Agent | `Claude Agent` | `agent@local` | Agent vault writes: `capture_knowledge`, session summaries, hot.md updates |
| Auto-Sweep | `Auto-Sweep` | `sweep@local` | Hourly cron catch-all for uncommitted changes |

The user identity is whatever is set in the vault's local `git config`. The agent
and sweep identities are fixed strings; no configuration needed.

---

## Why Local-Only

The vault contains personal notes, PII, and sensitive research. A remote push would
require access controls, secret management, and trust decisions about which service
holds the data. Local git gives the full audit trail without those tradeoffs.

Sync across devices happens at the file level (iCloud, OneDrive, Syncthing), not via
git push/pull. Git history stays on each device. The per-device partitioning in
`vault-structure.md` ensures agents on different devices don't write to the same paths,
so sync conflicts are rare and typically cosmetic.

---

## Commit Conventions

Agent writes use `--author` to set the identity explicitly:

```bash
git add -A
git commit --author="Claude Agent <agent@local>" \
  -m "agent: session 2026-05-23 hybrid-search-tuning"
```

The Auto-Sweep cron runs hourly and commits any uncommitted changes:

```bash
git add -A
git commit --author="Auto-Sweep <sweep@local>" \
  -m "sweep: $(date +%Y-%m-%dT%H:%M) uncommitted changes"
```

If there's nothing to commit, the sweep exits silently (check `git status --short`
before committing to avoid empty commit errors).

---

## Filtering by Identity

To see all agent writes:

```bash
git log --author="agent@local" --oneline
```

To see a specific date range:

```bash
git log --author="agent@local" --after="2026-05-01" --before="2026-05-31" --oneline
```

To see what changed in a specific commit:

```bash
git show <commit-hash>
```

To see every commit that touched a specific note:

```bash
git log --follow --oneline -- "Agent/Knowledge/mac-mini/sqlite-vec-column-requirement.md"
```

---

## Per-File Provenance

In addition to git log, agent-written notes carry `last_agent_update` in frontmatter.
This field records the date of the last agent edit without requiring a git query.

Use cases:
- "Show me notes the agent hasn't updated since before 2026-01-01" (stale knowledge sweep)
- "Which notes did the agent write this week?" (session review)

`last_agent_update` is set by the agent on initial write and updated on each
subsequent agent edit. Human edits do not update it. This preserves the distinction
between "agent last touched this" and "someone last edited this file."

---

## Session Summaries as Receipts

Session summaries in `Agent/Sessions/<device-id>/` serve as the primary audit record
for agent activity. For any date range, you can answer:

- What sessions ran?
- What notes were created?
- What decisions were made?
- What was left unresolved?

The git log corroborates the summaries. If a summary says five notes were created and
the git commit for that session shows five new files, the record is consistent.

If the git commit and the summary don't match, the session summary is the more reliable
source (it was written by the agent at session end; the commit might have been swept
up later by Auto-Sweep).

---

## Recovering from Missing Commits

If Auto-Sweep or the agent failed to commit and the vault has uncommitted changes:

```bash
git status --short                        # See what's uncommitted
git add -A
git commit --author="Auto-Sweep <sweep@local>" -m "sweep: manual recovery $(date +%Y-%m-%dT%H:%M)"
```

Don't try to reconstruct which identity should own the recovery commit. Auto-Sweep
is the right author for catch-all commits. The session summaries will have the correct
attribution for the content.
