#!/usr/bin/env python3
"""tag-audit: scan vault frontmatter tags, group near-duplicates by edit distance,
output merge suggestions.

Usage:
    python3 tag-audit.py [vault-path]

Requires: python-frontmatter (already in requirements.txt)
"""
import os
import sys
from collections import defaultdict
from pathlib import Path

import frontmatter

SKIP_DIRS = {".obsidian", ".git", ".vault-config", ".DS_Store", ".trash", ".stversions"}


def levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            ins = prev[j + 1] + 1
            dele = curr[j] + 1
            sub = prev[j] + (0 if ca == cb else 1)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]


def collect_tags(vault_path: str) -> dict[str, int]:
    """Walk vault, parse frontmatter, return {tag: file_count}."""
    counts: dict[str, int] = defaultdict(int)
    vault = Path(vault_path)
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = Path(root) / fname
            try:
                post = frontmatter.load(str(fpath))
            except Exception:
                continue
            tags = post.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            if not isinstance(tags, list):
                continue
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    counts[tag.strip()] += 1
    return dict(counts)


def group_near_duplicates(tags: list[str], threshold: int = 3) -> list[list[str]]:
    """Group tags where any pair has edit distance < threshold (transitive)."""
    # Union-Find grouping
    parent = {t: t for t in tags}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    for i, a in enumerate(tags):
        for b in tags[i + 1 :]:
            if levenshtein(a.lower(), b.lower()) < threshold:
                union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for tag in tags:
        groups[find(tag)].append(tag)

    return [sorted(g) for g in groups.values() if len(g) > 1]


def main() -> None:
    vault_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/ashco-vault")

    if not os.path.isdir(vault_path):
        print(f"Error: vault path not found: {vault_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning tags in: {vault_path}")
    print()

    counts = collect_tags(vault_path)
    if not counts:
        print("No tags found.")
        return

    all_tags = sorted(counts)
    print(f"Total unique tags: {len(all_tags)}")
    print()

    # Tag frequency report (top 20)
    print("=== Top 20 tags by file count ===")
    for tag, count in sorted(counts.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {count:4d}  {tag}")
    print()

    # Near-duplicate groups
    groups = group_near_duplicates(all_tags, threshold=3)
    if not groups:
        print("=== No near-duplicate tags found (edit distance < 3) ===")
        return

    print(f"=== Near-duplicate groups ({len(groups)} groups, edit distance < 3) ===")
    print("  Merge suggestion: keep the most frequent tag, rename the rest.")
    print()
    for group in groups:
        # Sort group by descending frequency
        group_sorted = sorted(group, key=lambda t: -counts.get(t, 0))
        keep = group_sorted[0]
        merges = group_sorted[1:]
        print(f"  Keep:   {keep!r} ({counts.get(keep, 0)} files)")
        for m in merges:
            print(f"  Merge:  {m!r} ({counts.get(m, 0)} files)")
        print()


if __name__ == "__main__":
    main()
