# CONTRACT.md — NexaSearch

> Any change to this file must be agreed by Nitesh and Shivai and go through a
> PR. Never change it silently.

This is the API boundary between the two halves of NexaSearch:
`app/` = Nitesh (product and user experience) and `engine/` = Shivai (crawl,
indexing, and retrieval). Each half is built against a mock of the other, using
the exact JSON shapes below.

---

## POST /query — the engine (Shivai)

Takes a plain-English search query and returns ranked NexaSearch documents.

### Request

```json
{
  "query": "How does attention work in transformers?",
  "top_k": 10,
  "use_vector": true,
  "use_rerank": true
}
```

- `query` must be a non-empty string.
- `top_k` is optional and defaults to `10`; the product may request up to `50`.
- `use_vector` and `use_rerank` are optional and default to `true`.

### Success response — 200

`results` are ranked document chunks. `score` is a ranking signal, not a
calibrated relevance probability.

```json
{
  "results": [
    {
      "rank": 1,
      "chunk_id": "chunk-001",
      "doc_id": "document-001",
      "title": "Attention Is All You Need",
      "url": "https://arxiv.org/abs/1706.03762",
      "heading": "Attention mechanisms",
      "snippet": "Attention lets a model weigh the most relevant tokens.",
      "score": 0.8421,
      "quality_score": 0.91
    }
  ],
  "duration_ms": 84
}
```

### Errors

All errors share one envelope: an `"error"` field naming the kind, plus a
human-readable `detail`.

**400 — invalid query:**

```json
{
  "error": "invalid_query",
  "detail": "query must be a non-empty string."
}
```

**503 — no usable index:**

```json
{
  "error": "index_unavailable",
  "detail": "No searchable index is available. Build the index first."
}
```

---

## POST /index — the product (Nitesh)

> **Nitesh: this is your endpoint — edit freely, then approve this file.**

Takes seed URLs and indexing options, then starts the crawl-to-index pipeline.

### Request

```json
{
  "urls": [
    "https://docs.python.org/3/",
    "https://arxiv.org/"
  ],
  "max_pages": 10,
  "max_depth": 2,
  "quality_threshold": 0.6
}
```

- `urls` must contain one or more absolute `http` or `https` URLs.
- `max_pages`, `max_depth`, and `quality_threshold` are optional runtime
  overrides.
- Crawling observes robots rules and configured crawl limits.

### Success response — 200

```json
{
  "status": "completed",
  "documents_indexed": 42,
  "chunks_indexed": 186,
  "duration_ms": 12400,
  "warnings": []
}
```

### Errors

**400 — invalid indexing request:**

```json
{
  "error": "invalid_urls",
  "detail": "Provide at least one absolute HTTP or HTTPS URL."
}
```

---

## Data type rules

- `results` is always present in a successful query response; no matches is
  `"results": []`.
- `rank` starts at `1` and is contiguous within a response.
- `score` and `quality_score` are numbers. All other result fields are strings
  except where explicitly shown otherwise.
- URLs are absolute HTTP(S) URLs.
- `duration_ms` is a non-negative integer.

## Ground rules

- Shivai's engine returns ranked retrieval data only. Answer generation,
  presentation, and UI decisions are Nitesh's product-side responsibility.
- Nitesh owns the product endpoint and Shivai owns the query-engine endpoint.
- The engine uses BM25 retrieval, optional vector retrieval, reciprocal-rank
  fusion, optional reranking, and a quality boost; implementation details may
  change without changing these response shapes.
- DuckDB data and BM25/vector index artifacts are a matched set; rebuild the
  index after manually replacing either one.
- This contract changes only by agreement between Nitesh and Shivai, via PR :)
