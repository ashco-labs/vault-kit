# vault-kit — Claude Code Context

This is the vault-kit **framework repo**, not a vault. You are editing the tools, protocol definitions, and skill implementations that other vaults and agents depend on.

---

## What Lives Where

| Directory | Role |
|---|---|
| `protocol/` | Data contracts. Changes here affect every vault-kit user. |
| `scripts/` | Python indexer (`indexer.py`), search CLI (`search.py`), bootstrap, utilities. |
| `mcp-server/` | MCP stdio server wrapping search and capture. Three tools: `search_vault`, `capture_knowledge`, `vault_stats`. |
| `adapters/claude-code/skills/` | Reference Claude Code skill implementations. These are examples, not required configuration. |
| `recipes/` | Agent-agnostic workflow docs. No Claude-specific assumptions. |
| `docs/` | Architecture and setup guide for humans setting up vault-kit. |

---

## Protocol Files

The `protocol/` directory defines data contracts for every vault-kit-managed vault:

- `frontmatter-schema.md` — required and optional fields for agent-written notes
- `vault-structure.md` — directory layout: strict (enforced) vs flexible (conventional)
- `capture-protocol.md` — Panning for Gold: ACT NOW / RESEARCH / PARK / KILL classification
- `search-defaults.md` — RRF parameters, BM25 weights, filter schema, embedding model defaults
- `audit-model.md` — three-identity git model (user / Claude Agent / Auto-Sweep)
- `session-summary-template.md` — session summary format and field notes
- `corpus-spec.yaml` — machine-readable corpus definitions

**Before editing protocol files:** changes are a contract break for existing vaults. Consider backward compatibility. If the change affects how existing notes are indexed or searched, document the migration path.

---

## Search Stack

sqlite-vec 0.1.9 + FTS5 + Ollama (nomic-embed-text, 768 dims). Hybrid search via RRF (k=60). Index at `~/.vault-index/<vault-name>.db` (outside vault, fully regenerable). See `protocol/search-defaults.md` for algorithm details and `docs/architecture.md` for the full design.

---

## Scripts

The indexer and search scripts are the reference implementation for any vault-kit-compatible tool. Key invariants:

- The index lives outside the vault (not in `.vault-config/`)
- Reindexing is always safe to run: idempotent, no data loss
- Filters are applied at the SQL layer before RRF, not post-hoc

---

## Adapters and Recipes

`adapters/claude-code/skills/` — Claude Code-specific skill implementations. These call the MCP server or fall back to CLI scripts. They are reference implementations: users can install them as-is or adapt them.

`recipes/` — workflow docs with no platform assumptions. Any agent (Claude, Copilot, Codex, custom) can follow them using CLI scripts when MCP is unavailable.

---

## Working in This Repo

This is a public repo. Others will fork and use it. Before committing:

- Protocol changes: backward compatibility check
- Script changes: verify the CLI interface is stable (other agents may call it directly)
- MCP server changes: keep tool names and parameter schemas stable
- Recipe changes: keep them agent-agnostic (no Claude-specific syntax, no vault-kit-specific paths)
- Adapter changes: document which vault-kit version the adapter targets

The MCP server's three tool contracts (`search_vault`, `capture_knowledge`, `vault_stats`) are the primary API surface. Treat them as a stable interface once v1.0 ships.
