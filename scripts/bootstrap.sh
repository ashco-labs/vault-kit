#!/usr/bin/env bash
# vault-kit bootstrap: first-run setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== vault-kit bootstrap ==="
echo

# 1. Check Python 3.10+
echo "[1/7] Checking Python version..."
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.10+ and retry."
  exit 1
fi
PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "ERROR: Python 3.10+ required. Found: $PY_VERSION"
  exit 1
fi
echo "  Python $PY_VERSION OK"

# 2. Create venv if needed, install deps
echo "[2/7] Setting up Python venv..."
VENV_DIR="$REPO_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "  Creating venv at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi
echo "  Installing dependencies from scripts/requirements.txt..."
"$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
echo "  Dependencies installed."

# 3. Check Ollama
echo "[3/7] Checking Ollama..."
if ! command -v ollama &>/dev/null; then
  echo
  echo "  ERROR: ollama not found. Install it first:"
  echo "    macOS:  brew install ollama"
  echo "    Linux:  curl -fsSL https://ollama.com/install.sh | sh"
  echo "    Or visit: https://ollama.com/download"
  echo
  exit 1
fi
OLLAMA_VERSION=$(ollama --version 2>&1 | head -1)
echo "  $OLLAMA_VERSION OK"

# 4. Pull nomic-embed-text
echo "[4/7] Pulling nomic-embed-text model..."
if ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
  echo "  nomic-embed-text already present."
else
  echo "  Pulling nomic-embed-text (this may take a few minutes)..."
  ollama pull nomic-embed-text
fi

# 5. Get vault path
echo "[5/7] Vault path..."
if [ $# -ge 1 ]; then
  VAULT_PATH="$1"
else
  DEFAULT_VAULT="$HOME/ashco-vault"
  read -rp "  Enter vault path [default: $DEFAULT_VAULT]: " VAULT_INPUT
  VAULT_PATH="${VAULT_INPUT:-$DEFAULT_VAULT}"
fi
VAULT_PATH="${VAULT_PATH%/}"  # strip trailing slash

if [ ! -d "$VAULT_PATH" ]; then
  echo "  ERROR: vault path not found: $VAULT_PATH"
  exit 1
fi
echo "  Vault: $VAULT_PATH"

# 6. Create ~/.vault-index/ dir
echo "[6/7] Ensuring ~/.vault-index/ exists..."
mkdir -p "$HOME/.vault-index"
echo "  Ready: $HOME/.vault-index/"

# 7. Run initial full index
echo "[7/7] Running initial full index..."
echo
START_TIME=$(date +%s)
VAULT_NAME=$(basename "$VAULT_PATH")
DB_PATH="$HOME/.vault-index/${VAULT_NAME}.db"

"$VENV_DIR/bin/python3" "$SCRIPT_DIR/indexer.py" "$VAULT_PATH" --full --db "$DB_PATH"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo
echo "=== Bootstrap complete ==="
DB_SIZE=$(du -sh "$DB_PATH" 2>/dev/null | awk '{print $1}' || echo "unknown")
echo "  Vault:           $VAULT_PATH"
echo "  DB:              $DB_PATH ($DB_SIZE)"
echo "  Embedding model: nomic-embed-text"
echo "  Time:            ${ELAPSED}s"
echo
echo "To search your vault:"
echo "  .venv/bin/python3 scripts/search.py '$VAULT_PATH' 'your query'"
