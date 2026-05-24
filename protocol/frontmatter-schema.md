# Frontmatter Schema

All agent-written notes carry a universal frontmatter block. Per-corpus fields extend it. Human notes are exempt; this schema is enforced only on agent-written paths.

## Universal Fields

Every agent-written note, regardless of corpus:

```yaml
---
title: string                     # Human-readable title (sentence case, no trailing period)
type: atomic | wiki | research | report | session | daily | clipping | entity | diagram
source: human | agent:claude-code | agent:copilot | reader-sync | notion-sync | teams-sync
projects: [string]                # Optional. Project slugs: ["001-monarch-review"]. Omit if none.
domain: string                    # Optional. Loose category: personal-finance, engineering, cooking, etc.
tags: [string]                    # 5-15 tags. Reuse existing tags via existing-tags.sh before coining new ones.
created: YYYY-MM-DD
related: [string]                 # Optional. Wikilinks to related notes: ["[[note-name]]"]
last_agent_update: YYYY-MM-DD    # Date of the last agent edit. Human edits don't update this field.
confidence: high | medium | low   # Optional. For agent-authored findings and research. Omit for factual notes.
superseded_by: string             # Optional. Wikilink to the replacement note if this one is stale.
---
```

### Field Notes

**title** — matches the filename without the date prefix. For atomic notes, the title states the claim or finding directly: `"SQLite FTS5 does not support phrase proximity by default"`, not `"FTS5 notes"`.

**type** — controls which template is applied and which corpus the note belongs to:
- `atomic`: a single finding, pattern, or decision. Write-once, superseded when stale. Goes to Agent/Knowledge/.
- `wiki`: maintained reference doc. Updated in place across sessions (not superseded). Goes to Agent/Wiki/.
- `research`: synthesis of external sources on a bounded topic. Goes to Agent/Research/.
- `report`: internally generated analysis (audits, critiques, health snapshots). Goes to Agent/Reports/.
- `session`: session summary with decisions, outcomes, open threads. Goes to Agent/Chats/.
- `daily`: dated daily note. Human-authored; rarely written by agent.
- `clipping`: saved web or reader content. Goes to Capture/.
- `entity`: person, project, or organization stub. Goes to Entities/.
- `diagram`: Mermaid or structured diagram. Goes to Agent/Artifacts/.

**source** — who wrote the note. Agent sources use the `agent:<id>` prefix so git blame and search can filter by origin.

**tags** — 5 minimum, 15 maximum. Use nouns and short phrases, not verbs. Prefer existing tags (run `scripts/existing-tags.sh` before writing). Tags are not a controlled vocabulary; near-duplicates get merged periodically by `scripts/tag-audit.py`.

**last_agent_update** — set on initial write, updated on each agent edit. Human edits in Obsidian don't touch this field. Lets you filter for "notes the agent touched recently" without walking git log.

**superseded_by** — when a finding is wrong or outdated, write a replacement note and set this field on the old one. Don't delete the old note; the supersession chain is provenance.

---

## Per-Corpus Extensions

Fields added on top of the universal block for specific corpora.

### Agent/Knowledge/

```yaml
confidence: high | medium | low   # Required here; optional elsewhere
superseded_by: string             # Required when stale
```

### Agent/Wiki/

```yaml
# No additional required fields beyond universal.
# Reference docs are updated in place; use last_agent_update to track freshness.
# Optional: superseded_by if the entire reference doc is replaced (rare).
```

### Agent/Research/

```yaml
source_type: research | paste-in | agent-generated
topic: string                     # One-line research question or topic
sources_consulted: [string]       # URLs, note wikilinks, or "conversation transcript"
as_of: YYYY-MM-DD                 # When the research was current
```

### Agent/Reports/

```yaml
report_type: audit | critique | health | review
scope: string                     # What was audited/reviewed: "apps/capture pipeline", "monarch rules Q2"
```

### Agent/Chats/

```yaml
session_started: YYYY-MM-DDTHH:MM  # ISO 8601, local time
duration: string                    # Human-readable: "2h 15m"
notes_created: [string]             # Wikilinks to all notes written this session
transcript: string                  # Relative path to JSONL: "transcripts/2026-05-23-slug.jsonl"
```

### Capture/reader/

Reader-sync writes these fields; don't overwrite them in agent notes:

```yaml
reader_id: string
reader_url: string
reader_labels: [string]
highlight_count: integer
reader_state: active | archived | later
```

### Projects/ (project index notes)

```yaml
state: active | dormant | done | archived
started: YYYY-MM-DD
last_touched: YYYY-MM-DD
summary: string                   # One-sentence project description
```

### Entities/

Entity stubs are minimal. Often just type + tags:

```yaml
type: entity
entity_type: person | organization | project | tool
```

---

## Granularity Guide

Which note shape to use:

| Content | Shape | Lifecycle |
|---|---|---|
| Stable reference (architecture, recurring patterns, conventions) | One note per topic, updated in place | `superseded_by` when replaced |
| Volatile finding (bug, discovery, action item) | One atomic note per finding | `superseded_by` chain |
| Research on a bounded topic | One research report per session | Standalone; linked from session summary |
| Session output | One session summary per session | Index links to all notes + reports |
| Draft / working material | `working-note` type | Promoted to `atomic` or `research` when ready |

---

## Backlogged Fields

`ai_summary` — one-sentence LLM-generated summary for the search index. Not in MVP. Will be added when the indexer gains a summarization pass.
