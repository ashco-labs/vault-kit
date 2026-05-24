---
name: vault-kit-update
description: Check for and apply vault-kit protocol updates at session start
triggers:
  - session start (low-priority background check, before vault context load)
  - "check for vault-kit updates" / "update vault-kit"
  - "is vault-kit up to date"
---

## When to Check

Check once per session at session start, before loading vault context. The check is
a dry-run fetch (cheap, read-only). Skip it if:

- The user said "no updates this session" or "skip the update check"
- You already checked earlier in the same session
- The vault-kit clone path isn't configured or the clone doesn't exist (fail silently,
  note once if relevant)

Don't re-check mid-session. One check at the start is enough.

---

## Step 1: Check for New Commits

```bash
git -C <vault-kit-path> fetch --dry-run 2>&1
```

If the output is empty: local clone is current. No further action; proceed with the
session.

If the output shows new refs (e.g., `refs/heads/main -> origin/main` with commit
hashes): proceed to Step 2.

`<vault-kit-path>` is wherever vault-kit is cloned. Common locations:
`~/repos/vault-kit/`, `~/tools/vault-kit/`. If the path isn't set in vault
configuration, ask the user once at first encounter.

---

## Step 2: Read the Changelog Diff

```bash
git -C <vault-kit-path> fetch origin
git -C <vault-kit-path> diff HEAD..origin/main -- protocol/CHANGELOG.md
```

Read the diff to understand:
- What changed (new recipes, protocol updates, adapter changes, bug fixes)
- Whether any changes affect the user's vault setup
- Whether any changes are breaking (format changes, removed fields, renamed paths)

---

## Step 3: Present Changes and Ask for Approval

Summarize the diff concisely. Name the specific files that changed and what the changes
mean for the workflow.

Example:
```
vault-kit has 2 new commits. Changes:
- protocol/capture-protocol.md: Added `source_type` field to RESEARCH note frontmatter
- recipes/session-capture.md: Added quality checklist at end of Panning for Gold flow

The `source_type` field is new. Existing RESEARCH notes won't have it; they still work
but won't pass updated frontmatter validation.

Apply this update? (yes / skip / defer)
```

Wait for explicit user approval before pulling. Protocol and format changes can affect
how notes are written to the vault; an unapproved change applied mid-session creates
inconsistency with notes already written this session.

---

## Step 4: Apply the Update

On user approval:

```bash
git -C <vault-kit-path> pull
```

After pulling, diff what changed in the recipe and adapter files:

```bash
git -C <vault-kit-path> diff HEAD~<n>..HEAD -- recipes/ adapters/
```

Where `<n>` is the number of new commits applied.

---

## Step 5: Propose Harness Skill Updates

Compare changed recipe and adapter content against the user's local harness skills.
For Claude Code users, this is `.agents/core/skills/` in the platform harness.

For each changed file:
1. Read the updated vault-kit file.
2. Read the corresponding local harness skill (if one exists).
3. Identify what's different.
4. Propose a specific edit: show old content and new content side by side.

Present each change separately. Don't bundle multiple skill updates into one proposal.
The user approves or rejects each independently.

If a local harness skill has diverged significantly from the vault-kit adapter (the user
customized it), call out the divergence explicitly. Don't overwrite custom content.

---

## Breaking Changes

If the changelog indicates a breaking change, surface it explicitly before asking for
approval. Describe:
- What changed
- What vault notes are affected (search the vault to estimate scope)
- What migration looks like (a script, bulk update, or note-by-note)

Offer to write a migration if one is needed. Write a session note describing what
changed and what was migrated, even with user approval.

---

## References

- `protocol/CHANGELOG.md` (vault-kit root) — full change history
- `recipes/vault-kit-update.md` — full update detection and application recipe
- `adapters/claude-code/` — the Claude Code-specific adapter files that may need updating
