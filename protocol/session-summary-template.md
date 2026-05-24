# Session Summary Template

Copy this template to `Agent/Chats/<device-id>/YYYY-MM-DD-<slug>.md` at session end.
Fill in every section; omit sections that genuinely don't apply (a 20-minute triage
session won't have Decisions or Rejected Alternatives).

Target 20-50 lines. Scale to complexity: a short triage session lands at the low
end, a multi-hour research session at the high end. The goal is a searchable
receipt, not a narrative.

---

## Template

```markdown
---
title: "<Brief description of what the session accomplished>"
type: session
source: agent:<id>
created: YYYY-MM-DD
session_started: YYYY-MM-DDTHH:MM
duration: "Xh Ym"
notes_created:
  - "[[note-slug-1]]"
  - "[[note-slug-2]]"
  - "[[research-report-slug]]"
transcript: "transcripts/YYYY-MM-DD-slug.jsonl"
tags: [session, <domain>, <project-slug>]
last_agent_update: YYYY-MM-DD
---

## Decisions

- <Decision 1. State what was decided and why, in one sentence.>
- <Decision 2.>

## Rejected Alternatives

- <Alternative 1>: <one-line reason it was rejected>
- <Alternative 2>: <one-line reason>

## Notes Captured

- [[note-slug-1]] — <one-line description>
- [[note-slug-2]] — <one-line description>
- [[research-report-slug]] — <one-line description>

## Open Threads

- <Unresolved question or next step 1>
- <Blocked item 2, including what's blocking it>
```

---

## Field Notes

**notes_created** — list every atomic note, research report, and artifact written during this session. This is the receipt. If a note isn't linked here, the session summary doesn't prove it happened.

**transcript** — path to the agent session JSONL relative to the vault root. If no JSONL was saved (e.g. the agent platform doesn't export transcripts), omit the field rather than leaving it empty.

**duration** — wall-clock time, not active time. Estimate if the agent platform doesn't provide exact times.

**Decisions** — things that were decided and won't be re-litigated. If a decision is worth capturing as an atomic note (architecture, convention), write the atomic note and link it here.

**Rejected Alternatives** — brief. The point is to prevent re-litigating the same ground in a future session. One line per alternative is enough.

**Notes Captured** — mirrors `notes_created` but with one-line descriptions so a reader can scan the list without opening each note.

**Open Threads** — what didn't finish. A future session picks these up via `hot.md` or searches for this summary. Be specific: "needs decision on X" is useful; "follow up later" is not.

---

## Minimal Example (Short Session)

```markdown
---
title: "Fixed sqlite-vec missing column error in reindex.sh"
type: session
source: agent:claude-code
created: 2026-05-23
session_started: 2026-05-23T14:30
duration: "35m"
notes_created:
  - "[[sqlite-vec-column-requirement]]"
transcript: "transcripts/2026-05-23-reindex-fix.jsonl"
tags: [session, engineering, vault-kit]
last_agent_update: 2026-05-23
---

## Decisions

- Added `embedding BLOB` column to `notes` table migration. sqlite-vec requires it at
  table creation, not as an extension column.

## Notes Captured

- [[sqlite-vec-column-requirement]] — sqlite-vec requires embedding column at table creation, not ALTER TABLE

## Open Threads

- Verify reindex performance after schema change (didn't benchmark this session)
```

---

## Full Example (Complex Session)

```markdown
---
title: "vault-kit hybrid search: RRF fusion + FTS5 weight tuning"
type: session
source: agent:claude-code
created: 2026-05-23
session_started: 2026-05-23T09:00
duration: "2h 45m"
notes_created:
  - "[[rrf-k-parameter-tradeoffs]]"
  - "[[fts5-title-weight-multiplier]]"
  - "[[bm25-negative-score-convention]]"
  - "[[sqlite-vec-cosine-perf-10k]]"
  - "[[search-weight-v1-decision]]"
transcript: "transcripts/2026-05-23-hybrid-search.jsonl"
tags: [session, engineering, vault-kit, search]
last_agent_update: 2026-05-23
---

## Decisions

- RRF k=60 adopted as default. Lower values (k=10, k=20) over-emphasized
  rank differences between similar-quality results in test queries.
- Title weight set to 10x, tags to 5x, content to 1x. Matches standard
  document retrieval heuristics; can be tuned per-vault via config.
- No hard similarity threshold. RRF naturally down-weights low-quality results
  without a cutoff that would discard edge cases.

## Rejected Alternatives

- k=10 for RRF: amplified noise from low-quality BM25 matches in early testing
- Cosine threshold at 0.7: cut too many valid results in sparse embedding spaces
- Equal weights across fields: title matches were drowned out by content matches

## Notes Captured

- [[rrf-k-parameter-tradeoffs]] — RRF k=60 vs k=10 behavior on sparse vs dense result sets
- [[fts5-title-weight-multiplier]] — How to apply column-weight multipliers in FTS5 MATCH queries
- [[bm25-negative-score-convention]] — FTS5 BM25 scores are negative; sort ASC for relevance
- [[sqlite-vec-cosine-perf-10k]] — Research: sqlite-vec exact cosine at 10K vectors (~80ms on M4)
- [[search-weight-v1-decision]] — Decision record for v1 search weight configuration

## Open Threads

- Test RRF on vault with >5K notes (only tested at ~500 this session)
- Check if FTS5 column weights interact with the `porter` tokenizer (suspected no effect, unconfirmed)
- sqlite-vec int8 quantization: worth evaluating for large vaults
```
