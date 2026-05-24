# vault-kit

Your second brain, but AI agents can read and write to it too.

vault-kit is an agent-agnostic PKM framework built on Obsidian. It gives any AI agent a structured vault to search, write to, and maintain across sessions. Search runs locally with sqlite-vec + FTS5 + Ollama. No cloud, no subscription, no vendor lock-in.

---

## Quick Start

```bash
git clone https://github.com/your-username/vault-kit ~/vault-kit
cd ~/vault-kit
bash scripts/bootstrap.sh --vault ~/my-vault
python scripts/search.py "your query" --vault ~/my-vault
```

Three commands. If bootstrap completes without errors, your vault is indexed and searchable.

---

## How It Works

**Vault structure.** Your notes live in a structured Obsidian vault. The `Agent/` directory is where agents write. `Capture/`, `Daily/`, `Entities/`, and `Synced/` are owned by you or external sync processes. Everything follows the protocol in `protocol/`.

**Search stack.** Queries hit two indexes simultaneously: FTS5 BM25 for keyword and exact-term matching, sqlite-vec cosine similarity for semantic matching. Results are fused via Reciprocal Rank Fusion (RRF). The embedding model runs locally via Ollama (default: `nomic-embed-text`, 768 dimensions). The index lives at `~/.vault-index/<vault-name>.db` and can be fully regenerated from vault content.

**MCP server.** `mcp-server/` exposes three tools over stdio: `search_vault`, `capture_knowledge`, and `vault_stats`. Wire it into your agent's MCP config and the agent can search and write to the vault directly.

**Session protocol.** At session start, an agent loads `Agent/hot.md` plus the current daily note and any relevant project context. At session end, it runs Panning for Gold: classify each finding as ACT NOW, RESEARCH, PARK, or KILL. ACT NOW and RESEARCH findings go to atomic notes in `Agent/Knowledge/`. A session summary goes to `Agent/Sessions/`. Then commit.

---

## Vault Structure

```
my-vault/
├── .vault-config/              → symlink to vault-kit/protocol/
│
├── Agent/                      agents write here
│   ├── hot.md                  cross-session state (always at this path)
│   ├── Knowledge/<device-id>/  atomic notes per device
│   ├── Research/<device-id>/   research reports per device
│   ├── Reports/<device-id>/    audit/review reports per device
│   ├── Sessions/<device-id>/   session summaries per device
│   └── Artifacts/<device-id>/  diagrams and structured outputs
│
├── Capture/
│   ├── reader/                 reader-sync writes here (agents: read only)
│   └── web/                    web clippings
│
├── Daily/                      user-authored daily notes (agents: read only)
├── Projects/NNN-name/          project directories
├── Entities/People|Companies|Concepts/
├── Synced/notion|meetings|email|bookmarks/
└── Archive/
```

Strict directories (`Agent/`, `Capture/reader/`) are owned by vault-kit tooling. Flexible directories (`Projects/`, `Archive/`) follow conventions but allow reorganization.

---

## Setup Prompt

Give this prompt to your agent to initialize vault-kit:

```
I have vault-kit cloned at ~/vault-kit. Set up my vault at ~/my-vault using the vault-kit protocol.

1. Run `bash ~/vault-kit/scripts/bootstrap.sh --vault ~/my-vault --device-id <your-device-name>`
2. Verify search works: `python ~/vault-kit/scripts/search.py "test" --vault ~/my-vault`
3. Add the MCP server to my agent config (see ~/vault-kit/docs/setup-guide.md for the JSON block)
4. Confirm the vault index is populated and at least one test search returns results

Device ID should be a short human-readable name like "mac-mini" or "laptop".
```

---

## Directory Reference

| Directory | Contents |
|---|---|
| `protocol/` | Shared conventions: frontmatter schema, vault structure, capture protocol, search defaults, session templates |
| `scripts/` | Python indexer, search CLI, bootstrap, utility scripts |
| `mcp-server/` | MCP stdio server: `search_vault`, `capture_knowledge`, `vault_stats` |
| `adapters/claude-code/skills/` | Reference skill implementations for Claude Code |
| `recipes/` | Agent-agnostic workflow docs: session capture, project context loading, research workflow, hot.md management |
| `examples/` | Minimal vault examples (forthcoming) |
| `docs/` | Architecture overview and setup guide |

---

## Agent Support

**Claude Code.** The MCP server wires directly into `~/.claude.json`. Skills in `adapters/claude-code/skills/` give Claude Code native workflows for vault search, capture, and hot.md management. See `docs/setup-guide.md` for the MCP config block.

**GitHub Copilot CLI and other agents.** The `recipes/` directory has agent-agnostic workflow docs. When MCP is not available, use the CLI directly:

```bash
# Search
python ~/vault-kit/scripts/search.py "query" --vault ~/my-vault

# Capture a note
python ~/vault-kit/scripts/capture.py --vault ~/my-vault \
  --title "Finding title" \
  --type atomic \
  --tags sqlite,search \
  --body "Note body here."
```

Agents can adapt the recipes into their native skill or workflow format. The protocol files in `protocol/` define the data contracts; the recipes define the workflows.

**Other MCP-compatible agents.** Any agent that supports stdio MCP servers can use `mcp-server/`. The three tools (`search_vault`, `capture_knowledge`, `vault_stats`) expose the full vault search and write surface.

---

## Credits

Patterns and inspiration from:
- Nate B. Jones, [Open Brain (OB1)](https://github.com/nbjones/open-brain) — agent-writable vault architecture
- Tiago Forte, [Building a Second Brain](https://www.buildingasecondbrain.com/) — PARA context bundle pattern

---

## License

MIT. See `LICENSE`.
