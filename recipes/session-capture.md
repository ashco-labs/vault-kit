# Session Capture

How to run Panning for Gold at session end and write the results to the vault.

This is the primary capture workflow. Every agent session ends with this recipe unless
the session was read-only (no findings to capture) or explicitly interrupted by the user.

---

## When to Run

Run this recipe when:

- The user signals the session is ending ("done", "thanks", "wrap up", "/shutdown")
- The agent detects a topic shift that closes off the current work
- A session time limit is reached
- The current task is fully complete and no new work has been started

Don't wait until the last possible moment. If findings are clear mid-session, you can
pre-write atomic notes then and reference them in the session summary at the end.

---

## Process

### Step 1: Evaluate Findings

Walk through the session's key observations, discoveries, and decisions. Classify each
one against the four categories from `capture-protocol.md`:

**ACT NOW** — The finding is immediately actionable. Concrete next steps are clear.
A future agent could pick this up tomorrow and know exactly what to do.

**RESEARCH** — Worth keeping as reference, but not immediately actionable. A future
session on this topic would benefit from this note existing.

**PARK** — Possibly useful if this topic recurs, but not worth the note overhead now.
Let it die with the transcript.

**KILL** — Wrong, irrelevant, or superseded during this session. If a previous vault
note states the opposite, mark it `superseded_by` pointing to the correction.

When in doubt: PARK. The vault should contain findings that passed the "actually matters"
test, not a transcript dump.

---

### Step 2: Write ACT NOW Notes

For each ACT NOW finding, write one atomic note to `Agent/Knowledge/<device-id>/`.

Filename: `YYYY-MM-DD-<slug>.md` where the slug describes the finding in 3-5 words.

Required frontmatter (per `frontmatter-schema.md`):

```yaml
---
title: "<The finding, stated as a fact or action>"
type: atomic
source: agent:<your-id>
tags: [5-15 tags, prefer existing tags]
created: YYYY-MM-DD
confidence: high | medium | low
last_agent_update: YYYY-MM-DD
---
```

Body: 3-10 sentences. Include:
- What's true (the finding itself)
- What to do next (the concrete action)
- Where it came from (provenance: URL, tool output, user statement)

Example:

```markdown
---
title: "monarch-mcp 401 errors require token refresh before retry"
type: atomic
source: agent:claude-code
tags: [monarch-mcp, auth, 401, retry, token-refresh]
created: 2026-05-23
confidence: high
last_agent_update: 2026-05-23
---

The monarch-mcp server raises on 401 without attempting a token refresh. Any
caller that gets a 401 must call `refresh_monarch_token` and retry the original
request before surfacing the error to the user.

Next step: add retry logic in `mcps/monarch/src/client.ts` before re-raising.

Source: observed during monarch-review session; confirmed in server error logs.
```

---

### Step 3: Write RESEARCH Notes

For concise findings (a single fact, pattern, or conclusion), write an atomic note to
`Agent/Knowledge/<device-id>/` with `type: research`. Same format as ACT NOW, without
the action item in the body.

For bounded investigations (you explored a topic and produced a reference document),
write a research report to `Agent/Research/<device-id>/`. See the
research-workflow.md recipe for the research report format.

If research reports were written mid-session (the right time for them), verify their
frontmatter is complete. Update `as_of` if you made revisions.

---

### Step 4: Write Session Summary

After all notes are written, write the session summary to
`Agent/Sessions/<device-id>/YYYY-MM-DD-<slug>.md`.

Use `session-summary-template.md` as the template. The key sections:

- **Decisions** — what was decided and won't be re-litigated
- **Rejected Alternatives** — what was considered and rejected (prevents future sessions
  from re-litigating the same ground)
- **Notes Captured** — one-line description per note written this session
- **Open Threads** — what didn't finish; specific enough that a future session can pick up

The `notes_created` frontmatter field must list every note written this session as a
wikilink. This is the receipt: if a note isn't linked here, the session record doesn't
prove it happened.

Target length: 20-50 lines. A short triage session lands at the low end; a multi-hour
investigation at the high end.

---

### Step 5: Update hot.md

Rewrite `Agent/hot.md` to reflect the current state after this session.

Remove threads that resolved this session. Add new cross-session threads or blockers.
Keep it under 50 lines. See hot-md-management.md for the full hot.md format and
update rules.

---

### Step 6: Commit

Commit all vault changes using the agent identity:

```bash
git add -A
git commit --author="Claude Agent <agent@local>" \
  -m "agent: session YYYY-MM-DD <slug>"
```

The slug should match the session summary filename slug. Example:
`agent: session 2026-05-23 monarch-mcp-auth-fix`

PARK and KILL items: no vault writes. They die with the transcript.

---

## Quality Checklist

Before closing:

- Did you evaluate every significant finding, not just the obvious ones? Edge cases,
  failed approaches, and rejected alternatives are often the most valuable to capture.
- Do all ACT NOW notes have a concrete next step? A finding without an action is a
  RESEARCH item, not an ACT NOW.
- Do all RESEARCH notes have provenance? "I think" is not provenance. Name the source.
- Does the session summary link every note written this session in `notes_created`?
- Does hot.md reflect the state after this session (not before)?
- Is the commit authored as `Claude Agent <agent@local>`?

---

## PARK and KILL

These categories produce no vault output. The decision is the action.

For KILL items where a vault note states the opposite: write a correction note (RESEARCH
or ACT NOW), then set `superseded_by` on the old note pointing to the correction. Don't
delete the old note. The supersession chain is provenance.

---

## References

- `capture-protocol.md` — the four categories in detail, with examples
- `session-summary-template.md` — session summary template and field notes
- `frontmatter-schema.md` — all frontmatter fields and per-corpus extensions
- `vault-structure.md` — directory paths and per-device partitioning rules
- `audit-model.md` — git commit identity conventions
