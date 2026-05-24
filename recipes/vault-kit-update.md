# vault-kit Update Detection and Application

How an agent detects that vault-kit has new commits, presents the changes to the user,
and proposes updates to the local harness skills.

This is agent-first: the agent detects, reads, and proposes. No npm publish, no plugin
registry, no automatic application.

---

## When to Check

Check for vault-kit updates at session start, before loading vault context.

The check is cheap (a dry-run fetch). Skip it if:
- The user explicitly said "no updates this session"
- You already checked earlier in the same session
- The vault-kit path isn't configured or the clone doesn't exist

---

## Step 1: Check for New Commits

Fetch from the vault-kit remote without applying changes:

```bash
git -C <vault-kit-path> fetch --dry-run 2>&1
```

If the output is empty, the local clone is up to date. No further action.

If the output shows new commits (you'll see refs like `refs/heads/main -> origin/main`
with commit hashes), proceed to Step 2.

`<vault-kit-path>` is wherever vault-kit is cloned on disk. Common locations:
`~/repos/vault-kit/`, `~/tools/vault-kit/`, or wherever the user configured during
setup. If the path isn't known, ask the user once and remember it for the session.

---

## Step 2: Read the Changelog Diff

Pull the remote CHANGELOG without applying other changes:

```bash
git -C <vault-kit-path> fetch origin
git -C <vault-kit-path> diff HEAD..origin/main -- CHANGELOG.md
```

Read the diff to understand:
- What changed (new recipes, protocol updates, adapter changes, bug fixes)
- Whether any changes affect the user's current vault setup
- Whether any breaking changes require action on the user's side

---

## Step 3: Present Changes to the User

Summarize the changelog diff for the user. Be specific: name the files that changed and
what the changes mean for their workflow.

Example:

```
vault-kit has 3 new commits since your last update. Changes:

- recipes/session-capture.md: Added quality checklist section
- protocol/frontmatter-schema.md: Added `source_type` field to Agent/Research/ spec
- adapters/claude-code/capture-knowledge.md: Updated to use new source_type field

The `source_type` field is new. Any Agent/Research/ notes written before this update
won't have it; they'll still work but won't pass the new frontmatter validation.

Apply this update? (yes / skip / defer)
```

Wait for explicit user approval before pulling. This is a one-way door if any changes
affect how the agent writes to the vault: a format change applied mid-session can
create inconsistency with notes already written.

---

## Step 4: Apply the Update

On user approval:

```bash
git -C <vault-kit-path> pull
```

After pulling, diff the files that changed against the user's local harness skills:

```bash
git -C <vault-kit-path> diff HEAD~<n>..HEAD -- recipes/ adapters/
```

Where `<n>` is the number of new commits. This shows exactly what recipe and adapter
content changed.

---

## Step 5: Propose Harness Skill Updates

Compare the changed recipe and adapter content against the user's local harness skills
(for Claude Code users: `.agents/core/skills/` or the equivalent in their harness).

For each changed file:

1. Read the updated vault-kit file.
2. Read the corresponding local harness skill.
3. Identify what's different.
4. Propose a specific edit: show the old content and the new content.

Present each proposed change separately. Don't bundle multiple skill updates into a
single proposal. The user should be able to approve or reject each change independently.

Example:

```
The capture-knowledge adapter changed. Here's the proposed update to
.agents/core/skills/capture/SKILL.md:

OLD (line 42-45):
  source: agent:<id>

NEW:
  source: agent:<id>
  source_type: research | paste-in | agent-generated

Apply this change? (yes / skip)
```

If the local harness skill diverges significantly from the vault-kit adapter (the user
has customized it), note the divergence and let the user decide. Don't overwrite
custom content silently.

---

## What Not to Do

**Don't auto-apply updates without user approval.** Protocol and adapter changes can
affect how the agent writes to the vault. An unapproved format change applied to a live
vault creates inconsistency.

**Don't apply all skill changes as a batch.** Each change gets its own approval step.
The user may want some changes and not others.

**Don't fail loudly if the vault-kit clone doesn't exist.** If the path isn't configured
or the clone is missing, skip the check and continue with the session. Mention it once
if it seems relevant.

**Don't check for updates more than once per session.** One check at session start is
enough. Don't re-check mid-session unless the user explicitly asks.

---

## Handling Breaking Changes

Some vault-kit updates introduce breaking changes: format changes that make old notes
non-compliant, removed fields, renamed directories.

If the changelog indicates a breaking change:
- Surface it explicitly before asking for approval
- Describe what notes are affected and how many (search the vault for notes in the
  affected corpus)
- Offer to write a migration: a script or agent task that updates affected notes in bulk

Breaking changes should never be applied silently. Even with user approval, write a
session note describing what changed and what was migrated.

---

## Version Tracking

vault-kit includes a `version.json` at the repo root:

```json
{
  "version": "0.3.1",
  "released": "2026-05-23"
}
```

After pulling an update, record the new version in the vault's `.vault-config/` if
the setup includes a local config file. This lets you quickly answer "what version of
vault-kit is this vault running?" without checking git.

If no local version tracking is configured, the git log on the vault-kit clone is the
source of truth: `git -C <vault-kit-path> log --oneline -1`.

---

## References

- `CHANGELOG.md` (vault-kit root) — full change history
- `version.json` (vault-kit root) — current version
- `adapters/` — platform-specific adapter files that may need updating
- `recipes/` — the recipe files themselves, which this workflow keeps current
