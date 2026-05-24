---
name: vault-orient
description: Load vault context at session start. Reads hot.md, recent daily notes, recent chat digests, detects project scope, runs a vault search for the user's objective.
triggers:
  - session start (invoke before any other work)
  - "where were we" / "what's active" / "orient me"
  - resuming work after a break
  - "/orient"
---

# vault-orient: session start context loading

Load the vault's active state into the session before doing any work. This is
the first thing that fires, before responding to the user's message.

## Why this exists

Without orientation, each session starts cold. The agent doesn't know what
happened yesterday, what's in flight, or what the user has been reading.
Orientation closes that gap in one pass, token-budgeted to ~2K so it doesn't
crowd out the actual work.

## Procedure

### 1. Read Agent/hot.md

This is the cross-session state file. Contains: currently active work, recent
session summaries (last 4-6), next likely action, open threads.

If hot.md is missing or empty, note it and continue (first session after setup).

### 2. Read recent daily notes

```bash
ls ~/ashco-vault/Daily/ | sort | tail -3
```

Read the last 3 daily notes (if they exist). These are the user's handwritten
notes from recent days. Scan for mentions of projects, people, or topics that
might be relevant.

If Daily/ is empty or doesn't exist, skip.

### 3. Read recent chat digests

```bash
ls ~/ashco-vault/Agent/Chats/<device-id>/ | sort | tail -3
```

Read the last 3 chat digests. These show what the agent worked on in recent
sessions: decisions, outcomes, open threads.

### 4. Detect project scope

Scan the user's first message for project references:
- Explicit NNN prefix: "work on 001-monarch-review"
- Project name mention: "the monarch stuff", "level up algos"
- File path containing Projects/NNN: ~/ashco-vault/Projects/002-level-up-algos/

If a project is detected, load all .md files in that project directory
(respect the 20-file / 15K-token soft limit from vault-structure.md).

### 5. Vault search for objective

Extract the user's objective from their first message and run:

```
search_vault(query=<objective>, top_k=10)
```

Present results concisely: "Found N relevant items." Flag any results that
have highlights (the user marked those passages as important). Note source
types so the user knows if results come from their reading (Capture/reader/)
vs agent knowledge vs wiki pages.

### 6. Present orientation summary

One short block at the top of your first response:

```
**Orientation**
- Active: <from hot.md>
- Recent: <1-line per last 2-3 sessions>
- Project loaded: <NNN-name> (N files) or "none detected"
- Vault hits: N results for "<objective>"
```

Then proceed to answer the user's actual message.

## Token budget

Target ~1.5-2K tokens for all orientation content combined. If a project
directory is large, read the index.md first and selectively load other files
based on relevance to the user's message.

## When to skip

- User explicitly says "skip orientation" or "don't load context"
- The message is a quick one-off question unrelated to ongoing work
- The session is a subagent dispatch (context provided by the controller)

## When to re-orient mid-session

If the user mentions a different project mid-conversation ("let's switch to
the monarch stuff"), run steps 4-5 for the new project. Don't re-read hot.md
or daily notes.
