# Project Context Loading

How to load project context at session start and how to detect and load project context
when a project comes up mid-session.

---

## Session Start: What to Load

At the start of every agent session, load this baseline context before doing any work:

1. **`Agent/hot.md`** — cross-session state from prior sessions. Read this first. It
   tells you what was in progress, what was blocked, and what threads need to continue.

2. **Last 3-5 daily notes** (`Daily/YYYY-MM-DD.md`) — recent context from the user's
   perspective. Helps orient to what's been happening in the user's world outside
   agent sessions.

3. **Relevant prior knowledge** — search the vault with a query derived from the session
   objective. Pull notes, research reports, and session summaries that are likely to be
   relevant. 10-15 results is typically enough; expand if the topic is broad.

Present what you found: "Found N relevant items. X have your highlights or annotations."
This surfaces prior work without requiring the user to remember what they've written.

---

## Detecting Project Context

A project is in scope when the user's message references a project slug.

Project slugs follow the pattern `NNN-project-name` where `NNN` is a zero-padded number
(e.g. `001-monarch-review`, `042-vault-kit-build`). Watch for this pattern:

- Explicit slug: "let's work on 003-vault-kit-build"
- Partial name: "pick up vault-kit" (match against known project dirs)
- Project index note title: "open the vault-kit project"
- Reference to a project's artifact or subdirectory

Detection should apply to any message in the session, not just the first. A user may
introduce a project mid-session after starting with a general question.

---

## Loading a Project

When a project is detected, load the following:

**Project index note** (`Projects/<NNN-name>/index.md`): This is the entry point. It
contains the project's state, summary, and links to key notes. Read it first.

**Active project notes**: Read the other `.md` files in `Projects/<NNN-name>/`, excluding
`Archive/`. These are the working documents, plans, and decisions for the project.

**Related vault knowledge**: Search the vault with a project-focused query (the project
name or domain). This surfaces atomic notes and research reports written during prior
project sessions that may not be in the project directory itself.

Present what you found: the project state from the index note, a count of active files,
and any highly relevant prior research.

---

## Size Guidance

Keep project directories lean. When loading a project, the agent reads all active files
in the project directory. If the directory is too large, the agent either under-reads
(losing context) or blows the context budget.

Guidelines (from `vault-structure.md`):
- Under 20 files per project directory (not counting `Archive/`)
- Under 15K tokens of total content across active notes

If a project directory approaches these limits, help the user move completed material:
- Finished sub-artifacts: move to `Projects/<slug>/Archive/`
- Large reference documents: move to `Agent/Research/<device-id>/` with a `projects:`
  frontmatter field linking back to the project slug

These limits are soft. The goal is a project directory that fits comfortably in context,
not an arbitrary file count.

---

## Project Index Note

Every project directory should have an `index.md` with the Projects/ frontmatter schema:

```yaml
---
title: "<Project name>"
type: working-note
source: human
projects: ["NNN-project-name"]
tags: [5-15 tags]
created: YYYY-MM-DD
state: active | dormant | done | archived
started: YYYY-MM-DD
last_touched: YYYY-MM-DD
summary: "<One-sentence project description>"
last_agent_update: YYYY-MM-DD
---
```

The `state` field is the project's current status. Check it when loading:
- `active`: normal work in progress
- `dormant`: paused; check open threads before starting new work
- `done`: completed; usually read-only unless reopening
- `archived`: historical; don't add new files

---

## When No Project Is Detected

If the session has no clear project scope, skip project loading. Load only:
- `Agent/hot.md`
- Last 3-5 daily notes
- Vault search results relevant to the session objective

Don't force a project label onto work that doesn't have one. Not every session
belongs to a project.

---

## What Not to Do

**Don't load the entire vault.** The search step surfaces relevant prior work; don't
substitute breadth for relevance. 10-15 search results covers most sessions.

**Don't skip the vault search.** Even when a project is detected, prior research may
live outside the project directory. The search step catches notes that mention the
project's domain without the project frontmatter field.

**Don't load `Archive/` subdirectories** unless the user is explicitly looking for
historical material. Archive content is read-only and usually not relevant to active work.

**Don't update `last_touched` on the project index** unless you've done meaningful work
in the project this session. Loading for context doesn't count.

---

## Example: Session Start

A user opens a session and says: "let's continue the vault-kit search implementation."

1. Read `Agent/hot.md`. See: "Open thread: sqlite-vec int8 quantization — didn't finish
   last session."
2. Read last 3 daily notes.
3. Search the vault: "vault-kit search sqlite-vec FTS5". Get 12 results including
   two research reports from prior sessions.
4. Detect project: "003-vault-kit-build". Load `Projects/003-vault-kit-build/index.md`
   and 7 active project files.
5. Present: "Found 12 relevant vault items from prior sessions. Open thread from last
   session: sqlite-vec int8 quantization. Project state: active. 7 active project files
   loaded. Ready to continue."

---

## References

- `vault-structure.md` — Projects/ directory layout, size guidelines
- `frontmatter-schema.md` — Projects/ frontmatter schema (state, summary, last_touched)
- `hot-md-management.md` — what hot.md contains and when it's updated
- `search-defaults.md` — search algorithm and default parameters
