# Vault Structure

The directory layout for a vault-kit-managed Obsidian vault.

Two zones: **strict** and **flexible**.

Strict directories are owned by vault-kit tools. Agents write to them; the names and
hierarchy are fixed. Renaming or reorganizing a strict directory breaks tool assumptions.

Flexible directories follow documented conventions, but users can add subdirectories,
rename personal folders, or reorganize without breaking vault-kit. The structure below
documents the conventions; only the strict ones are enforced.

---

## Directory Tree

```
vault-root/
├── .vault-config/              → symlink to vault-kit/protocol/
│
├── Agent/                      [STRICT]
│   ├── hot.md                  Cross-session state (single-writer, always at this path)
│   ├── Knowledge/
│   │   └── <device-id>/        Per-device atomic findings (write-once, superseded)
│   ├── Reference/
│   │   └── <device-id>/        Per-device maintained docs (updated in place)
│   ├── Research/
│   │   └── <device-id>/        Per-device external source synthesis
│   ├── Reports/
│   │   └── <device-id>/        Per-device audit/review reports
│   ├── Sessions/
│   │   └── <device-id>/        Per-device session summaries
│   └── Artifacts/
│       └── <device-id>/        Per-device diagrams and structured outputs
│
├── Capture/                    [STRICT: agent writes blocked]
│   ├── reader/                 Reader-sync (home: Readwise archive)
│   ├── notion/                 Notion-sync (home: Notion DB mirrors)
│   ├── web/                    User-captured web clippings
│   ├── meetings/               (work: Teams meeting summaries)
│   └── email/                  (work: email action items)
│
├── Daily/                      [STRICT: agent writes blocked]
│   └── YYYY-MM-DD.md           One file per day, user-authored
│
├── Projects/                   [FLEXIBLE]
│   └── NNN-project-name/       One dir per project (NNN- numeric prefix)
│       ├── index.md            Project index note (Projects/ frontmatter schema)
│       ├── <working notes>
│       └── Archive/            Finished sub-artifacts within the project
│
├── Entities/                   [STRICT: agent writes blocked]
│   ├── People/
│   ├── Companies/
│   └── Concepts/               Maps of Content linking related notes
│
└── Archive/                    [FLEXIBLE]
    └── <anything>              Completed, shelved, or historical material
```

---

## Strict Directories

Agents write to these paths. The names are not negotiable.

| Path | Owner | Notes |
|---|---|---|
| `Agent/` | vault-kit | All subdirs; do not rename |
| `Agent/hot.md` | agent (single-writer) | Always at this exact path |
| `Agent/Knowledge/<device-id>/` | agent (per-device) | Atomic findings, write-once |
| `Agent/Reference/<device-id>/` | agent (per-device) | Maintained docs, edit-in-place |
| `Agent/Research/<device-id>/` | agent (per-device) | External source synthesis |
| `Agent/Reports/<device-id>/` | agent (per-device) | |
| `Agent/Sessions/<device-id>/` | agent (per-device) | |
| `Agent/Artifacts/<device-id>/` | agent (per-device) | |
| `Capture/` | sync + user | All subdirs; agents must not write here |
| `Daily/` | user | Agents must not write here |
| `Entities/` | user | Agents must not write here |
| `.vault-config/` | vault-kit | Symlink to vault-kit/protocol/; don't replace with a dir |

---

## Per-Device Partitioning

Agents write notes under a device-specific subdirectory to prevent conflicts when
the vault is synced across multiple machines (iCloud, OneDrive, Syncthing, etc.).

The device ID is a short, stable identifier set during vault-kit setup:

```
Agent/Knowledge/mac-mini/
Agent/Knowledge/laptop/
Agent/Sessions/mac-mini/
```

Rules:
- One agent session runs on one device. A session writes only to its own `<device-id>/` subtree.
- `Agent/hot.md` is the exception: single-writer, no partitioning. The last-write-wins
  when synced. Conflicts are rare because hot.md updates happen at session boundaries,
  not mid-session. If a conflict occurs, keep the newer version.
- Don't use UUIDs or hostnames as device IDs. Short human-readable names (`mac-mini`,
  `laptop`, `work-mbp`) make `git log` and search output readable.

---

## Projects Directory

Project directories use a numeric prefix for consistent sort order and stable slugs:

```
Projects/
├── 001-monarch-review/
├── 002-level-up-algos/
└── 003-vault-kit-build/
```

Each project directory contains an `index.md` using the Projects/ frontmatter schema.
The project slug (`001-monarch-review`) is the value used in the `projects:` frontmatter
field on any note related to that project.

### Context Bundle Size

Keep project directories lean. An agent loading a project for context reads the index
note and a subset of the project's notes. If the project directory grows too large,
the agent either under-reads (missing context) or over-reads (blowing the context budget).

Guidelines:
- Under 20 files per project directory (not counting Archive/ subdirs)
- Under 15K tokens of total content across the project's active notes
- Archive finished sub-artifacts to `Projects/<slug>/Archive/` or vault-level `Archive/`

These are soft limits. Enforce them by moving completed material to Archive/, not by
splitting a project into arbitrary shards.

---

## .vault-config/

A symlink to the `protocol/` directory of the vault-kit installation:

```bash
ln -s /path/to/vault-kit/protocol .vault-config
```

This makes the protocol files accessible from within the vault without duplicating them.
Obsidian will treat `.vault-config/` as a folder of markdown files (the `.md` protocol
files will be visible and searchable in Obsidian, but that's fine; they're reference docs).

Do not replace the symlink with a real directory. If you need to override a protocol
default, put the override in `.vault-config/overrides/` (a real directory inside the
symlinked protocol dir, which will be part of vault-kit itself when that feature ships).

---

## What's Not Here

Files and directories that don't fit these categories go wherever makes sense for the
user. vault-kit does not enforce structure outside the strict directories.

Common additions:
- `Resources/` — reference documents, PDFs, images
- `Templates/` — Obsidian templates for user-created notes
- `Inbox/` — quick-capture landing zone before processing
- `Maps/` — MOCs (maps of content) and index notes

Adding these does not break vault-kit. They'll be indexed (if they contain valid
frontmatter with `created`) and searchable alongside the structured corpus.
