# Research Workflow

How to run a research session with vault capture: when to write, where to write, and
how research output integrates with session capture at the end.

---

## Two Moments for Writing

Research produces two types of output, written at two different moments:

**Research reports** — written mid-session, as the investigation unfolds. These are
working documents. Write them when you have enough to say, not when the session ends.
They go in `Agent/Research/<device-id>/`.

**Atomic notes** — written at session end, via Panning for Gold. These are distilled
findings extracted from the research. They go in `Agent/Knowledge/<device-id>/`.

The session summary links both. It's the receipt that proves both types of output exist.

---

## Before Starting Research

Search the vault for prior work on the topic before writing anything new.

Search with an objective, topic-focused query. Examples:
- "sqlite-vec cosine similarity performance"
- "FTS5 BM25 negative scores"
- "Ollama embedding API batching"

Check the results for:
- Research reports that already cover the question (update or link them, don't duplicate)
- Atomic notes with relevant findings (reference them with `[[wikilinks]]`)
- Session summaries that mention the topic (check their open threads)

If prior work exists, read it first. The goal is to extend knowledge, not to re-derive
facts the vault already holds.

---

## Writing a Research Report Mid-Session

When you have a bounded investigation with a clear topic and enough findings to write
about, create a research report. Don't wait for session end.

**When to create a new report vs. update an existing one:**
- New topic or new question: create a new file.
- Adding findings to a prior session's investigation on the same topic: update the
  existing file (update `as_of` and `last_agent_update`).

### File location

`Agent/Research/<device-id>/YYYY-MM-DD-<slug>.md`

The slug describes the topic in 3-5 words: `sqlite-vec-cosine-perf`, `ollama-embed-api-batching`.

### Required frontmatter

```yaml
---
title: "<Research question or topic, phrased as a question or topic statement>"
type: research
source: agent:<your-id>
source_type: research | paste-in | agent-generated
tags: [5-15 tags, prefer existing tags]
created: YYYY-MM-DD
topic: "<One-line research question>"
sources_consulted:
  - "<URL, tool name, or '[[wikilink]]' to a related note>"
  - "conversation transcript"
as_of: YYYY-MM-DD
confidence: high | medium | low
last_agent_update: YYYY-MM-DD
---
```

**source_type** — which kind of input produced this document:
- `research`: you ran queries, fetched docs, synthesized findings
- `paste-in`: the user provided raw content; you organized and extracted it
- `agent-generated`: derived from reasoning or prior session knowledge, no external lookup

**as_of** — when the research was current. Update this if you revise the report in a
later session. Readers use this to assess staleness.

**sources_consulted** — list every source that informed the findings: URLs, tool names
(e.g. "sqlite-vec README", "Context7 Obsidian docs"), wikilinks to vault notes, or
"conversation transcript" if the findings came from user statements.

### Body structure

```markdown
## Question

<What you set out to find out. One paragraph.>

## Findings

<Bulleted list of findings. Each bullet is a complete, portable fact.>
<Use [[wikilinks]] to reference related vault notes.>

## Recommendation

<Optional. What to do given these findings.>

## Open Questions

<What you didn't resolve this session. Specific enough that a future session can pick up.>
```

Keep the body dense and skimmable. A research report is reference material, not a
narrative. Use headings, bullets, and code blocks to make findings scannable.

---

## Using Wikilinks

Reference known entities, projects, and vault concepts with `[[wikilinks]]`. This keeps
the knowledge graph connected without duplicating content.

When to use wikilinks:
- Referencing a vault note by its slug: `[[sqlite-vec-column-requirement]]`
- Referencing a project: `[[003-vault-kit-build]]`
- Mentioning a concept that has or should have its own note: `[[rrf-fusion]]`

Don't wikilink external URLs or raw strings. Use the markdown link format for those:
`[sqlite-vec README](https://github.com/asg017/sqlite-vec)`.

---

## At Session End

At session end, run Panning for Gold (see session-capture.md). Research items from
the session fall into two buckets:

**Mid-session research reports already written:** Verify their frontmatter is complete.
Update `as_of` if you made revisions during the session. Link them in the session
summary's `notes_created` field.

**Concise findings not worth a full report:** Write as atomic notes to
`Agent/Knowledge/<device-id>/` with `type: atomic` or `type: research`. These are
single facts or patterns that stand alone.

The line between "atomic note" and "research report" is length and scope: 3-10 sentences
is an atomic note; a bounded investigation with a question, findings, and open questions
is a research report.

---

## What Not to Do

**Don't wait until session end to write research reports.** They're working documents.
Write them when you have enough to say. The session summary links them at the end.

**Don't duplicate prior vault research.** Search first. If a prior report exists, update
it or reference it. Duplicate reports with slightly different findings create confusion
about which is current.

**Don't write research reports for PARK items.** If a finding isn't worth an atomic note,
it isn't worth a report. The four-category evaluation in session-capture.md applies to
research output too.

**Don't omit sources.** "I know this" is not provenance. Name the source: a URL, a doc
page, a tool output, or "derived from conversation transcript." Future sessions evaluating
whether findings are still current need to know where they came from.

---

## References

- `session-capture.md` — Panning for Gold at session end, including atomic note format
- `capture-protocol.md` — four-category evaluation (ACT NOW / RESEARCH / PARK / KILL)
- `frontmatter-schema.md` — full frontmatter reference for Agent/Research/ corpus
- `vault-structure.md` — directory paths and per-device partitioning
