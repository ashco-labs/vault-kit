#!/usr/bin/env bash
# Auto-sweep: commit uncommitted vault changes as sweep@local
VAULT="${1:-$HOME/ashco-vault}"
cd "$VAULT" || exit 1

# Only proceed if there are changes
if [ -n "$(git status --porcelain)" ]; then
  N=$(git status --porcelain | wc -l | tr -d ' ')
  git add -A
  git commit --author="Auto-Sweep <sweep@local>" \
    -m "chore(vault): auto-sweep — $N files"
  echo "Committed $N files as Auto-Sweep"
else
  echo "Nothing to commit"
fi
