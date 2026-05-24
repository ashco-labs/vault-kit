# Setup Guide

Step-by-step instructions for setting up vault-kit on a new machine.

---

## Prerequisites

- Python 3.10 or later
- [Ollama](https://ollama.com) installed and running
- Git (for vault history)
- Obsidian (optional but recommended for browsing your vault)

Verify:
```bash
python3 --version    # should show 3.10+
ollama --version     # should show a version string
git --version
```

---

## Step 1: Clone vault-kit

```bash
git clone https://github.com/your-username/vault-kit ~/vault-kit
```

vault-kit lives at `~/vault-kit`. You can put it anywhere; the paths below assume this location. Adjust if yours differs.

---

## Step 2: Choose a Vault Location

Pick a directory for your vault. It does not need to exist yet; bootstrap will create it.

```bash
export VAULT=~/my-vault
export DEVICE_ID=mac-mini    # short, human-readable name for this machine
```

Use a simple name for `DEVICE_ID`: `mac-mini`, `laptop`, `work-mbp`. This name appears in file paths and git log output, so keep it short and readable.

---

## Step 3: Run Bootstrap

```bash
bash ~/vault-kit/scripts/bootstrap.sh --vault $VAULT --device-id $DEVICE_ID
```

Bootstrap does:

1. Creates the vault directory structure (`Agent/`, `Capture/`, `Daily/`, etc.)
2. Creates `.vault-config/` as a symlink to `~/vault-kit/protocol/`
3. Writes `Agent/hot.md` with an empty state
4. Creates `~/vault-kit/scripts/requirements.txt` dependencies into a virtual env
5. Pulls the Ollama embedding model (`nomic-embed-text`)
6. Creates the SQLite index at `~/.vault-index/<vault-name>.db`
7. Runs an initial index pass over the vault (empty on first run)
8. Initializes a local git repo in the vault (`git init`)

Bootstrap is idempotent: running it again on an existing vault is safe.

If bootstrap fails at the Ollama step, make sure Ollama is running (`ollama serve`) and the model is available (`ollama pull nomic-embed-text`).

---

## Step 4: Verify Search

```bash
python ~/vault-kit/scripts/search.py "test query" --vault $VAULT
```

On a freshly bootstrapped vault, this returns 0 results (the vault is empty). That's correct. Verify that the command runs without errors and prints a results list (even if empty).

Add a test note to confirm indexing:

```bash
python ~/vault-kit/scripts/capture.py \
  --vault $VAULT \
  --title "vault-kit is set up" \
  --type atomic \
  --tags setup,vault-kit,test \
  --confidence high \
  --body "Initial setup complete. vault-kit is indexed and searchable."
```

Then search for it:

```bash
python ~/vault-kit/scripts/search.py "vault-kit setup" --vault $VAULT
```

You should see your test note in the results.

---

## Step 5: Configure Per-Device ID

The device ID must be available when the MCP server or CLI scripts run. Set it via environment variable:

```bash
export VAULT_DEVICE_ID=mac-mini
```

Add it to your shell profile so it persists:

```bash
echo 'export VAULT_DEVICE_ID=mac-mini' >> ~/.zshrc   # or ~/.bashrc
echo 'export VAULT_PATH=~/my-vault' >> ~/.zshrc
```

---

## Step 6: Wire the MCP Server

### Claude Code

Add vault-kit to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "vault-kit": {
      "type": "stdio",
      "command": "python",
      "args": ["~/vault-kit/mcp-server/server.py"],
      "env": {
        "VAULT_PATH": "~/my-vault",
        "VAULT_DEVICE_ID": "mac-mini"
      }
    }
  }
}
```

Restart Claude Code. The MCP server starts as a subprocess per session. Verify it's working by asking Claude to run `vault_stats`.

**Optional: Install Skills**

Copy the reference skills into your Claude Code skills directory:

```bash
cp -r ~/vault-kit/adapters/claude-code/skills/* ~/.claude/skills/
```

Or add them as a subpath in your project's `.claude/` directory. See the individual skill `SKILL.md` files for trigger phrases and usage.

### GitHub Copilot CLI

Copilot CLI does not currently support MCP. Use the CLI scripts directly:

```bash
# Search
python ~/vault-kit/scripts/search.py "your query" --vault ~/my-vault --top-k 15

# Capture
python ~/vault-kit/scripts/capture.py --vault ~/my-vault \
  --title "note title" \
  --type atomic \
  --tags tag1,tag2,tag3,tag4,tag5 \
  --body "note body"

# Index (run after manual additions)
python ~/vault-kit/scripts/indexer.py --vault ~/my-vault --device mac-mini
```

Refer to `recipes/` for workflow documentation adapted to CLI usage.

### Other MCP-Compatible Agents

Any agent that supports stdio MCP servers can use vault-kit. The general pattern:

```
command: python ~/vault-kit/mcp-server/server.py
args: (none)
env:
  VAULT_PATH: /path/to/your/vault
  VAULT_DEVICE_ID: your-device-id
```

The three tools (`search_vault`, `capture_knowledge`, `vault_stats`) are the full API surface. See `docs/architecture.md` for tool parameter schemas.

---

## Step 7: Set Up the Auto-Sweep Cron (Optional)

Auto-Sweep commits any uncommitted vault changes on a schedule. It provides a consistent git audit trail without requiring manual commits after Obsidian edits.

Add a crontab entry:

```bash
crontab -e
```

```cron
0 * * * * cd ~/my-vault && git status --short | grep -q . && git add -A && git commit --author="Auto-Sweep <sweep@local>" -m "sweep: $(date +%Y-%m-%dT%H:%M) uncommitted changes"
```

This runs hourly, commits only if there are changes, and exits silently otherwise.

---

## Reindexing

**Incremental reindex** (after adding notes via CLI or Obsidian):

```bash
python ~/vault-kit/scripts/indexer.py --vault ~/my-vault --device $DEVICE_ID
```

**Full rebuild** (after changing the embedding model or schema):

```bash
python ~/vault-kit/scripts/indexer.py --vault ~/my-vault --device $DEVICE_ID --rebuild
```

The index is outside the vault and fully regenerable. Running `--rebuild` drops and recreates it without touching vault files.

---

## Changing the Embedding Model

The default model is `nomic-embed-text` (768 dimensions). To switch:

1. Pull the new model: `ollama pull mxbai-embed-large`
2. Update `.vault-config/search.yaml` (create if it doesn't exist):
   ```yaml
   embedding_model: mxbai-embed-large
   embedding_dim: 1024
   ```
3. Rebuild the index: `python ~/vault-kit/scripts/indexer.py --rebuild`

The embedding dimension must match the model. Changing the model without rebuilding causes a dimension mismatch error on the first query.

---

## Troubleshooting

**Ollama not found / embedding fails**

Check that Ollama is running: `ollama serve` (or check your system services). Pull the model if missing: `ollama pull nomic-embed-text`.

**Index out of date (new notes not showing in search)**

Run `python ~/vault-kit/scripts/indexer.py --vault ~/my-vault --device $DEVICE_ID` to update the index incrementally.

**MCP server fails to start in Claude Code**

Check that the path in `~/.claude.json` is correct and that `VAULT_PATH` exists. Run the server manually to see errors:
```bash
VAULT_PATH=~/my-vault VAULT_DEVICE_ID=mac-mini python ~/vault-kit/mcp-server/server.py
```

**sqlite-vec not loading**

sqlite-vec ships as a loadable extension. If it fails to load, verify that `scripts/requirements.txt` was installed into the virtual environment and that the extension binary is present. Run `bash ~/vault-kit/scripts/bootstrap.sh` again to reinstall.

**Search returns 0 results on a non-empty vault**

The vault may not be indexed. Run `indexer.py` to build the index. If the index exists but results are empty, check that your notes have valid frontmatter (including a `created` date) by running `scripts/validate-vault.py --vault ~/my-vault`.

---

## Updating vault-kit

```bash
cd ~/vault-kit
git pull
bash scripts/bootstrap.sh --vault ~/my-vault --device-id $DEVICE_ID
```

Bootstrap is idempotent. It upgrades dependencies and runs any schema migrations. If the protocol files changed in a way that requires a reindex, bootstrap will prompt you or run it automatically.

See `recipes/vault-kit-update.md` for the full update workflow, including how to check for breaking changes.

---

## Directory Summary After Setup

```
~/vault-kit/           vault-kit framework repo
~/my-vault/            your vault (agent-managed content lives here)
~/.vault-index/        SQLite index (outside vault, regenerable)
```

The vault and the index are separate by design. Deleting `~/.vault-index/` and running the indexer rebuilds it. Deleting the vault itself removes your notes; no index backup needed because the index is derived from the vault.
