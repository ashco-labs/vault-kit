# vault-kit — Agent Context

This file is for non-Claude agents (GitHub Copilot CLI, Codex, and other tools). It explains how to work with this repo and how to use vault-kit in a vault.

---

## This Repo

vault-kit is a framework, not a vault. The files here define protocols, implement the search stack, expose an MCP server, and document workflows. You are editing tooling that other vaults depend on.

Key directories:

- `protocol/` — data contracts (frontmatter schema, vault structure, capture protocol, search parameters)
- `scripts/` — Python indexer and search CLI
- `mcp-server/` — MCP stdio server
- `recipes/` — workflow documentation for any agent
- `adapters/` — platform-specific skill implementations (currently: `claude-code/`)

---

## Protocol Files as Reference

When working inside a vault-kit-managed vault (not this repo), read the protocol files to understand the data contracts:

- **What frontmatter to write:** `protocol/frontmatter-schema.md`
- **Where to write notes:** `protocol/vault-structure.md`
- **What to capture at session end:** `protocol/capture-protocol.md`
- **How search works:** `protocol/search-defaults.md`
- **Git commit conventions:** `protocol/audit-model.md`

The `.vault-config/` symlink in a vault points at this `protocol/` directory, so you can also read these files as `.vault-config/<filename>.md` from inside the vault.

---

## Workflow Recipes

The `recipes/` directory has agent-agnostic workflow documentation. These are written without Claude-specific syntax and can be followed by any agent using the CLI scripts.

| Recipe | When to use |
|---|---|
| `session-capture.md` | At session end: Panning for Gold + note writing + session summary + hot.md update |
| `project-context-loading.md` | At session start: load hot.md, daily note, project context |
| `research-workflow.md` | When doing a bounded investigation and writing a research report |
| `hot-md-management.md` | When updating `Agent/hot.md` (cross-session state) |
| `vault-kit-update.md` | When updating vault-kit itself and re-syncing protocol files |

---

## Adapting Recipes to Your Platform

The recipes describe what to do, not how your platform invokes tools. To adapt a recipe:

1. Read the recipe from `recipes/<name>.md`
2. Map each step to your platform's native file-read/write/commit tools
3. Follow the frontmatter schema from `protocol/frontmatter-schema.md` for any notes you write
4. Use the directory conventions from `protocol/vault-structure.md` for file placement

For Claude Code: skills in `adapters/claude-code/skills/` are pre-adapted. Install by copying the skill directories into your Claude Code skills path.

---

## CLI Fallback (When MCP Is Unavailable)

If your platform does not support MCP, use the CLI scripts directly:

**Search the vault:**
```bash
python ~/vault-kit/scripts/search.py "your query" \
  --vault ~/my-vault \
  --top-k 15
```

**Search with filters:**
```bash
python ~/vault-kit/scripts/search.py "your query" \
  --vault ~/my-vault \
  --filter domain=engineering \
  --filter path_prefix=Agent/Knowledge/
```

**Index the vault (run after adding notes):**
```bash
python ~/vault-kit/scripts/indexer.py \
  --vault ~/my-vault \
  --device mac-mini
```

**Full reindex (if schema or embedding model changed):**
```bash
python ~/vault-kit/scripts/indexer.py \
  --vault ~/my-vault \
  --device mac-mini \
  --rebuild
```

**Capture a note:**
```bash
python ~/vault-kit/scripts/capture.py \
  --vault ~/my-vault \
  --title "Finding title" \
  --type atomic \
  --tags sqlite,search,indexing \
  --confidence high \
  --body "Note body text here."
```

---

## MCP Server Tools

When MCP is available, the server exposes three tools:

**`search_vault`**
- `query` (string, required): the search query
- `top_k` (integer, default 15): number of results
- `filters` (object, optional): `source_type`, `domain`, `project`, `created_after`, `path_prefix`

**`capture_knowledge`**
- `content` (string, required): note body
- `type` (string, required): `atomic` | `research` | `working-note`
- `title` (string, required): note title
- `tags` (array of strings, required): 5-15 tags
- `projects` (array of strings, optional): project slugs
- `domain` (string, optional): e.g. `engineering`, `personal-finance`
- `confidence` (string, optional): `high` | `medium` | `low`

**`vault_stats`**
- No parameters. Returns note count, index freshness, device info.

---

## Data Contracts

All agent-written notes must follow the frontmatter schema in `protocol/frontmatter-schema.md`. The minimum required fields:

```yaml
---
title: string
type: atomic | research | session | working-note
source: agent:<your-agent-id>
tags: [at least 5 tags]
created: YYYY-MM-DD
last_agent_update: YYYY-MM-DD
---
```

Agent-written notes go under `Agent/Knowledge/<device-id>/` (atomic), `Agent/Research/<device-id>/` (research reports), or `Agent/Sessions/<device-id>/` (session summaries). Do not write to `Capture/reader/`, `Daily/`, `Entities/`, or `Synced/` — those are user- or sync-owned.

---

## Git Model

The vault uses local git only (no remote push). Agent commits use a fixed identity:

```bash
git add -A
git commit --author="Claude Agent <agent@local>" \
  -m "agent: session YYYY-MM-DD <slug>"
```

Replace `Claude Agent` with your agent's identity if adapting. See `protocol/audit-model.md` for the full three-identity model.
