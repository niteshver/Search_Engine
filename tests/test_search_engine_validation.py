import numpy as np
import pytest

from unittest.mock import Mock

from src.search.engine import SearchEngine
from src.search.bm25_index import BM25Index


def create_test_engine():
    """Create a test engine without loading embedding models."""

    engine = SearchEngine.__new__(SearchEngine)

    engine.bm25_index = BM25Index()
    engine.embedder = Mock()
    engine.embeddings = np.empty((0, 0))
    engine.cross_encoder = None

    engine.save = Mock()

    return engine


def test_validate_chunks_removes_invalid_documents():

    chunks = [
        {
            "chunk_id": "c1",
            "text": "Python programming tutorial",
            "url": "https://example.com/python",
        },
        {
            "chunk_id": "c2",
            "text": "",
            "url": "https://example.com/empty",
        },
        {
            "chunk_id": "",
            "text": "Missing identifier",
            "url": "https://example.com",
        },
        {
            "chunk_id": "c3",
            "text": "Missing URL",
            "url": "",
        },
        None,
    ]

    valid = SearchEngine.validate_chunks(chunks)

    assert len(valid) == 1
    assert valid[0]["chunk_id"] == "c1"


def test_validate_chunks_removes_duplicates():

    chunks = [
        {
            "chunk_id": "c1",
            "text": "First document",
            "url": "https://example.com/1",
        },
        {
            "chunk_id": "c1",
            "text": "Duplicate document",
            "url": "https://example.com/2",
        },
        {
            "chunk_id": "c2",
            "text": "Second document",
            "url": "https://example.com/3",
        },
    ]

    valid = SearchEngine.validate_chunks(chunks)

    assert len(valid) == 2

    assert [chunk["chunk_id"] for chunk in valid] == [
        "c1",
        "c2",
    ]


def test_bm25_and_vectors_use_same_chunks():

    engine = create_test_engine()

    chunks = [
        {
            "chunk_id": "c1",
            "doc_id": "d1",
            "text": "Python programming tutorial",
            "url": "https://example.com/python",
            "title": "Python",
            "heading": "Introduction",
            "metadata": {"quality_score": 0.9},
        },
        {
            "chunk_id": "c2",
            "doc_id": "d2",
            "text": "",
            "url": "https://example.com/empty",
        },
        {
            "chunk_id": "c3",
            "doc_id": "d3",
            "text": "Machine learning tutorial",
            "url": "https://example.com/ml",
            "title": "Machine Learning",
            "heading": "Introduction",
            "metadata": {"quality_score": 0.8},
        },
    ]

    engine.embedder.embed_texts.return_value = np.array([
        [0.1, 0.2],
        [0.3, 0.4],
    ])

    engine.index(chunks)

    assert len(engine.bm25_index.chunks) == 2

    assert engine.embeddings.shape == (2, 2)

    assert [
        chunk["chunk_id"]
        for chunk in engine.bm25_index.chunks
    ] == ["c1", "c3"]

    engine.embedder.embed_texts.assert_called_once_with([
        "Python programming tutorial",
        "Machine learning tutorial",
    ])

    assert (
        engine.bm25_index.chunks[0]["metadata"]["quality_score"]
        == 0.9
    )

    engine.save.assert_called_once()


def test_index_detects_embedding_mismatch():

    engine = create_test_engine()

    chunks = [
        {
            "chunk_id": "c1",
            "text": "Python programming",
            "url": "https://example.com/1",
        },
        {
            "chunk_id": "c2",
            "text": "Machine learning",
            "url": "https://example.com/2",
        },
    ]

    # Incorrect: one embedding for two valid chunks.
    engine.embedder.embed_texts.return_value = np.array([
        [0.1, 0.2],
    ])

    with pytest.raises(ValueError, match="Index integrity"):
        engine.index(chunks)

    # A failed indexing operation must not save invalid data.
    engine.save.assert_not_called()

    assert engine.bm25_index.chunks == []