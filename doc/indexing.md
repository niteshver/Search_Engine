# Indexing

After document processing, NexaSearch builds optimized search indexes that enable fast and relevant retrieval across millions of technical documents.

Each processed document is assigned a unique document ID and enriched with metadata before indexing.

The indexing pipeline includes:

- Document ID generation
- Metadata indexing
- BM25 lexical indexing
- Dense embedding generation
- Vector indexing
- Hybrid index creation
- Incremental index updates

NexaSearch maintains both lexical and semantic indexes to support hybrid search, combining keyword matching with semantic retrieval for improved search quality.

---


## Indexing Pipeline

```text
Processed Document
        │
        ▼
Document ID Generation
        │
        ▼
Metadata Extraction
        │
        ▼
BM25 Index
        │
        ├──────────────┐
        ▼              ▼
Embedding Model   Vector Index
        │              │
        └──────┬───────┘
               ▼
        Search Index
```

---

## Index Size

The index is designed to scale efficiently as the document collection grows.

Features include:

- Incremental indexing
- Compressed index structures
- Hybrid lexical and vector indexes
- Efficient storage for large document collections

---

## Index Maintenance & Updates

To keep search results fresh, NexaSearch supports:

- Incremental document updates
- Re-indexing modified documents
- Removal of deleted documents
- Background index optimization
- Periodic embedding regeneration *(when required)*

---

## Search Performance

NexaSearch is designed for low-latency retrieval using:

- BM25 lexical search
- Dense vector search
- Hybrid retrieval
- Metadata filtering
- Cross-encoder reranking
- Efficient indexing structures