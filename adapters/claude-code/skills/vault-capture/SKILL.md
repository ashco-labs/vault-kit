---
name: vault-capture
description: Capture session knowledge via Panning for Gold evaluation at session end
triggers:
  - session end signals ("/shutdown", "we're done", "wrap up", "that's all for today")
  - "/capture" (explicit mid-session invocation)
  - after significant research or discovery work where findings should survive the session
---

## When to Run

**Session end (primary).** Run Panning for Gold at every session end that produced
findings, decisions, or research. Even short sessions (30 minutes) may yield one
ACT NOW note worth keeping.

**Explicit invocation.** If the user says "/capture" or "save what we found," run the
evaluation now. Don't wait for session end.

**After bounded research.** If a significant investigation completed mid-session
(not at the end), write the research report immediately while the findings are fresh.
The session summary links it at session end.

---

## Panning for Gold: The Evaluation

At session end, walk through what happened and classify each finding or observation.
The full protocol is in `protocol/capture-protocol.md`. Brief summary:

**ACT NOW** — immediately actionable; concrete next steps are clear. Write one atomic
note per finding to `Agent/Knowledge/<device-id>/`.

**RESEARCH** — worth remembering as reference, not immediately actionable. Write as
an atomic note (if concise) or a research report to `Agent/Research/<device-id>/`
(if it was a bounded investigation).

**PARK** — might be useful if the topic recurs, but not worth the note overhead now.
No vault write. Let it die with the transcript.

**KILL** — wrong, irrelevant, or superseded during this session. No vault write. If
a killed claim was previously in the vault, mark that note with `superseded_by`.

Most observations don't survive contact with "does this actually matter?" That's
correct. ACT NOW and RESEARCH are the keepers.

---

## Writing Notes via capture_knowledge

For each ACT NOW or RESEARCH finding, call:

```
capture_knowledge(
  content: "The finding. What's true, what to do (ACT NOW) or why it matters (RESEARCH).
            Source: where it came from.",
  type: "atomic",          # or "research" for bounded investigations
  projects: ["003-vault-kit-build"],   # optional; project slug from Projects/ dir
  domain: "engineering",               # optional; coarse topic area
  tags: ["sqlite", "fts5", "search"]  # concrete, reusable vocabulary
)
```

The MCP server writes the note to `Agent/Knowledge/<device-id>/` (atomic) or
`Agent/Research/<device-id>/` (research). The server assigns the device-id from
vault configuration; you don't need to specify it.

Use wikilinks when referencing other vault notes: `[[note-slug]]`. Cross-links make
future search more useful and the notes more navigable in Obsidian.

For atomic notes, keep the body to 3-10 sentences. If you need more, it's a research
report. See `protocol/capture-protocol.md` for note structure and frontmatter examples.

---

## Writing the Session Summary

After all notes are written, write the session summary. File it at
`Agent/Sessions/<device-id>/YYYY-MM-DD-<slug>.md`. Use the template in
`protocol/session-summary-template.md`.

Key fields:
- `notes_created`: wikilinks to every atomic note and research report written this session
- `Open Threads`: anything unresolved, blocked, or handed off

The session summary is the audit trail. A note not linked in `notes_created` might as
well not exist for the purposes of cross-session search.

---

## Updating hot.md

After the session summary is written, fully rewrite `Agent/hot.md` per
`recipes/hot-md-management.md`:

- Remove threads resolved this session
- Add new cross-session threads or blockers that emerged
- Update `Recently sessions` to include the just-written session summary
- Update `Next likely action` to reflect what should happen next
- Keep it under 150 lines; target 50-100

hot.md is a full overwrite each time. Do not append to it.

---

## Git Commit

After hot.md is written, commit all vault changes:

```bash
git add -A
git commit --author="Claude Agent <agent@local>" -m "agent: session $(date +%Y-%m-%d) <slug>"
```

Where `<slug>` is 2-4 words from the session's main topic (e.g., `hybrid-search-tuning`,
`reindex-bug-fix`). This commit is the durable record; everything before it (the transcript,
the in-session reasoning) is ephemeral.

---

## References

- `protocol/capture-protocol.md` — full Panning for Gold flow, note structure, and examples
- `protocol/session-summary-template.md` — session summary template with field notes
- `recipes/hot-md-management.md` — hot.md structure, write triggers, size discipline
- `protocol/vault-structure.md` — where notes go (Knowledge/ vs Research/ vs Sessions/)
