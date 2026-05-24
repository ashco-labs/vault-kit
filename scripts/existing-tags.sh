#!/usr/bin/env bash
# Scan vault frontmatter tags, output deduplicated list for classifier reuse-bias
VAULT="${1:-$HOME/ashco-vault}"
# Resolve symlink so BSD grep -r follows into iCloud/OneDrive-backed paths
VAULT_REAL="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$VAULT")"
grep -rh "^  - " "$VAULT_REAL" --include="*.md" | \
  grep -v "^  - \[" | \
  sed 's/^  - //' | \
  sort -u
