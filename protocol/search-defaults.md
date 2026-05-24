# Search Defaults

Default parameters for vault-kit's hybrid search. These are the starting values; per-vault
configuration can override them in `.vault-config/search.yaml`.

---

## Algorithm

Hybrid search combines FTS5 BM25 and sqlite-vec cosine similarity via Reciprocal Rank
Fusion (RRF). Neither signal alone is sufficient: BM25 handles exact-term and
keyword queries well but misses semantic matches; vector similarity handles paraphrases
and concept queries but struggles with proper nouns and exact strings. RRF fuses
both rank lists without requiring score normalization.

```
query
  ├── FTS5 MATCH query   →  BM25 rank list (top N candidates)
  └── sqlite-vec embed   →  cosine rank list (top N candidates)
                              ↓
                     RRF fusion (k=60)
                              ↓
                     top_k results
```

---

## Default Parameters

### Result Count

```yaml
top_k: 15
```

15 results covers most single-topic queries without overwhelming the context window.
Increase for broad exploration queries via the `--top-k` flag.

### RRF Fusion

```yaml
rrf_k: 60
```

The RRF formula for a document `d` with rank `r` in a rank list:

```
score(d) = 1 / (k + r)
```

Final score is the sum of RRF scores across all rank lists. `k=60` is the standard
value from the original RRF paper (Cormack, Clarke, Buettcher 2009). Lower values
(k=10, k=20) amplify rank differences and reward top-ranked items more aggressively;
higher values flatten the curve. At k=60, a rank-1 result scores ~1.6x a rank-10 result,
which is a reasonable weighting for most retrieval tasks.

Rationale for k=60: tested against k=10 and k=20 on sparse vault queries. Lower values
over-emphasized BM25 noise when the FTS candidate set contained weak matches. k=60
produced more stable results across query types.

### BM25 Field Weights

```yaml
bm25_weights:
  title: 10
  tags: 5
  content: 1
```

Applied as FTS5 column weights in the MATCH query. A title hit counts as 10 content
hits for BM25 scoring; a tags hit counts as 5.

Rationale: a note whose title matches the query is almost certainly relevant. Tags
encode curated vocabulary that's more precise than body text. Content is weighted
lowest because it's the highest-volume field and generates the most noise.

FTS5 applies these weights via the `columnsize` trick or the `bm25()` function's
weight arguments:

```sql
SELECT path, bm25(notes_fts, 10, 5, 1) AS score
FROM notes_fts
WHERE notes_fts MATCH ?
ORDER BY score ASC  -- BM25 is negative; lower = more relevant
LIMIT 100;
```

### Similarity Threshold

```yaml
similarity_threshold: null
```

No hard cosine threshold is applied. RRF naturally down-weights results that score
well in only one signal. A hard threshold would silently discard edge-case matches
in sparse embedding spaces; RRF handles this gracefully without a cutoff.

If the vault has a known low-quality embedding model, callers can apply a post-hoc
filter on the fused score. Don't bake it into the defaults.

---

## Filters

Filters narrow the candidate set before RRF fusion. Applied at the SQL layer, not
post-hoc, so they don't distort the rank lists.

```yaml
filters:
  source_type: string | null        # "reader-sync", "agent:claude-code", etc.
  domain: string | null             # "personal-finance", "engineering"
  project: string | null            # Project slug: "001-monarch-review"
  created_after: YYYY-MM-DD | null
  path_prefix: string | null        # "Agent/Knowledge/", "Capture/reader/", etc.
```

All filters are optional. Multiple filters are ANDed. The FTS5 and vector queries
both respect the same filter clause.

Example: search only within a project's notes, created after a specific date:

```sql
WHERE notes_fts MATCH ?
  AND project = '001-monarch-review'
  AND created >= '2026-04-01'
```

---

## Embedding Model

The default embedding model is Ollama-served. vault-kit ships with no preference on
which model; the user configures it in `.vault-config/search.yaml`. Common choices:

```yaml
embedding_model: nomic-embed-text   # 768-dim, fast, good general-purpose
# embedding_model: mxbai-embed-large  # 1024-dim, slower, better semantic recall
```

The embedding dimension must match the `notes` table schema. Changing the model
requires a full reindex (`scripts/reindex.sh --rebuild`).

---

## Performance Notes

At exact (non-ANN) cosine search with sqlite-vec:
- ~10K 768-dim vectors: ~80ms per query on M4 Mini
- ~30K vectors: ~240ms
- ~50K vectors: ~400ms

For vaults approaching 30K notes, pre-filtering the FTS5 result set to the top 500
BM25 candidates before running the vector scan keeps interactive latency under 200ms.
See `scripts/reindex.sh` for the two-pass query pattern.

sqlite-vec 0.1.x is exact-only. ANN indexing (HNSW) is on the roadmap but not
available in the current version.
