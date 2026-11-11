import os
import re
import numpy as np

from typing import List, Dict, Any

from src.config.settings import settings
from src.crawler.logger import logger
from src.search.bm25_index import BM25Index
from src.embedding.embedder import Embedder


class SearchEngine:

    def __init__(self):
        self.bm25_index = BM25Index()
        self.embedder = Embedder()
        self.cross_encoder = None
        self.embeddings: np.ndarray = np.empty((0, 0))

        # Load existing indexes if available
        self.load()

    # ============================================================
    # CROSS ENCODER
    # ============================================================

    def _load_cross_encoder(self):
        """Lazy load the Cross-Encoder model."""

        if self.cross_encoder is None:

            try:
                from sentence_transformers import CrossEncoder

                logger.info(
                    f"Loading Cross-Encoder model: "
                    f"{settings.CROSS_ENCODER_MODEL_NAME}..."
                )

                self.cross_encoder = CrossEncoder(
                    settings.CROSS_ENCODER_MODEL_NAME,
                    device="cpu"
                )

                logger.info("Cross-Encoder loaded successfully.")

            except Exception as e:

                logger.error(
                    f"Failed to load Cross-Encoder: {e}. "
                    "Reranking will be disabled."
                )

                self.cross_encoder = None

    # ============================================================
    # CHUNK VALIDATION
    # ============================================================

    @staticmethod
    def validate_chunks(
        chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Validate document chunks before indexing.

        Validation rules:
        1. Chunk must be a dictionary.
        2. Chunk must have a valid chunk_id.
        3. Chunk must contain non-empty text.
        4. Chunk must have a valid source URL.
        5. Duplicate chunk IDs are removed.

        Original document metadata and chunk ordering are preserved.
        """

        valid_chunks = []
        seen_ids = set()

        for chunk in chunks:

            # Check chunk type
            if not isinstance(chunk, dict):
                continue

            chunk_id = chunk.get("chunk_id")
            text = chunk.get("text")
            url = chunk.get("url")

            # Validate chunk ID
            if not isinstance(chunk_id, str):
                continue

            if not chunk_id.strip():
                continue

            # Validate searchable text
            if not isinstance(text, str):
                continue

            if not text.strip():
                continue

            # Validate source URL
            if not isinstance(url, str):
                continue

            if not url.strip():
                continue

            # Remove duplicate chunk IDs
            if chunk_id in seen_ids:
                continue

            seen_ids.add(chunk_id)

            # Preserve original chunk data
            valid_chunks.append(chunk)

        return valid_chunks

    # ============================================================
    # DOCUMENT INDEXING
    # ============================================================

    def index(self, chunks: List[Dict[str, Any]]):
        """
        Build BM25 and vector indexes using validated chunks.

        Ensures both indexes use exactly the same documents
        in exactly the same order.
        """

        # Step 1: Validate chunks
        valid_chunks = self.validate_chunks(chunks)

        if not valid_chunks:

            logger.warning("No valid chunks to index.")
            return

        logger.info(
            f"Indexing {len(valid_chunks)} valid chunks "
            f"out of {len(chunks)} received."
        )

        # Step 2: Generate embeddings
        logger.info(
            f"Generating embeddings for "
            f"{len(valid_chunks)} chunks..."
        )

        texts = [
            chunk["text"]
            for chunk in valid_chunks
        ]

        embeddings = np.asarray(
            self.embedder.embed_texts(texts)
        )

        # Step 3: Check embedding integrity
        if (
            embeddings.ndim != 2
            or embeddings.shape[0] != len(valid_chunks)
            or embeddings.shape[1] == 0
        ):

            raise ValueError(
                "Index integrity error: "
                f"Expected {len(valid_chunks)} embeddings, "
                f"received shape {embeddings.shape}."
            )

        # Step 4: Build BM25 index
        new_bm25 = BM25Index()

        new_bm25.index_documents(valid_chunks)

        # Step 5: Update indexes
        # Only replace existing indexes after successful validation.
        self.bm25_index = new_bm25
        self.embeddings = embeddings

        logger.info(
            f"Embeddings generated with shape: "
            f"{self.embeddings.shape}"
        )

        # Step 6: Save indexes
        self.save()

        logger.info(
            f"Successfully indexed {len(valid_chunks)} chunks."
        )

    # ============================================================
    # HYBRID SEARCH
    # ============================================================

    def search(
        self,
        query: str,
        top_k: int = 10,
        use_vector: bool = True,
        use_rerank: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute hybrid search:

        BM25 Search
             +
        Vector Search
             |
             v
        Reciprocal Rank Fusion
             |
             v
        Cross-Encoder Reranking
             |
             v
        Quality Boost
        """

        if not self.bm25_index.chunks:
            return []

        if not isinstance(query, str) or not query.strip():
            return []

        if top_k <= 0:
            return []

        # --------------------------------------------------------
        # 1. BM25 SEARCH
        # --------------------------------------------------------

        bm25_results = self.bm25_index.search(
            query,
            top_k=100
        )

        bm25_ranks = {
            result[0]["chunk_id"]: idx
            for idx, result in enumerate(bm25_results)
        }

        # --------------------------------------------------------
        # 2. VECTOR SEARCH
        # --------------------------------------------------------

        vector_results = []

        # Verify BM25 and vector index alignment
        vector_index_valid = (
            self.embeddings.ndim == 2
            and self.embeddings.shape[0]
            == len(self.bm25_index.chunks)
            and self.embeddings.size > 0
        )

        if use_vector and vector_index_valid:

            query_emb = np.asarray(
                self.embedder.embed_query(query)
            ).reshape(-1)

            if (
                query_emb.size > 0
                and query_emb.size == self.embeddings.shape[1]
            ):

                # Calculate embedding norms
                norm_embeddings = np.linalg.norm(
                    self.embeddings,
                    axis=1
                )

                norm_query = np.linalg.norm(query_emb)

                # Prevent division by zero
                norm_embeddings[norm_embeddings == 0] = 1.0

                norm_query = (
                    1.0
                    if norm_query == 0
                    else norm_query
                )

                # Calculate cosine similarities
                similarities = np.dot(
                    self.embeddings,
                    query_emb
                ) / (
                    norm_embeddings * norm_query
                )

                # Retrieve top 100 matching chunks
                top_indices = np.argsort(
                    similarities
                )[::-1][:100]

                for idx in top_indices:

                    sim = float(similarities[idx])

                    if sim > 0.0:

                        vector_results.append(
                            (
                                self.bm25_index.chunks[idx],
                                sim
                            )
                        )

        vector_ranks = {
            result[0]["chunk_id"]: idx
            for idx, result in enumerate(vector_results)
        }

        # --------------------------------------------------------
        # 3. RECIPROCAL RANK FUSION
        # --------------------------------------------------------

        k_rrf = 60

        rrf_scores = {}
        all_matches = {}

        # BM25 ranking contribution
        for chunk, _ in bm25_results:

            cid = chunk["chunk_id"]

            all_matches[cid] = chunk

            bm25_rank = bm25_ranks[cid]

            rrf_scores[cid] = (
                rrf_scores.get(cid, 0.0)
                + (1.0 / (k_rrf + bm25_rank))
            )

        # Vector ranking contribution
        for chunk, _ in vector_results:

            cid = chunk["chunk_id"]

            all_matches[cid] = chunk

            vec_rank = vector_ranks[cid]

            rrf_scores[cid] = (
                rrf_scores.get(cid, 0.0)
                + (1.0 / (k_rrf + vec_rank))
            )

        # Sort results by RRF score
        sorted_rrf = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Select top 30 candidates
        candidates = [
            all_matches[cid]
            for cid, _ in sorted_rrf[:30]
        ]

        if not candidates:
            return []

        # --------------------------------------------------------
        # 4. CROSS-ENCODER RERANKING
        # --------------------------------------------------------

        final_scores = {}

        if use_rerank and len(candidates) > 0:

            self._load_cross_encoder()

            if self.cross_encoder:

                try:

                    pairs = [
                        [query, candidate.get("text", "")]
                        for candidate in candidates
                    ]

                    ce_scores = self.cross_encoder.predict(
                        pairs
                    )

                    # Store reranking scores
                    for candidate, ce_score in zip(
                        candidates,
                        ce_scores
                    ):

                        final_scores[
                            candidate["chunk_id"]
                        ] = float(ce_score)

                except Exception as e:

                    logger.error(
                        f"Error during Cross-Encoder rerank: {e}. "
                        "Falling back to RRF."
                    )

                    final_scores = {}

            # Use RRF for missing or failed Cross-Encoder scores
            for cid, rrf_score in sorted_rrf[:30]:

                if cid not in final_scores:
                    final_scores[cid] = rrf_score

        else:

            # Use RRF scores directly
            for cid, rrf_score in sorted_rrf[:30]:
                final_scores[cid] = rrf_score

        # --------------------------------------------------------
        # 5. QUALITY BOOST
        # --------------------------------------------------------

        max_score = (
            max(final_scores.values())
            if final_scores
            else 1.0
        )

        min_score = (
            min(final_scores.values())
            if final_scores
            else 0.0
        )

        score_range = (
            max_score - min_score
            if max_score != min_score
            else 1.0
        )

        boosted_results = []

        for candidate in candidates:

            cid = candidate["chunk_id"]

            raw_score = final_scores[cid]

            normalized_score = (
                raw_score - min_score
            ) / score_range

            # Retrieve quality score
            quality_score = candidate.get(
                "metadata", {}
            ).get(
                "quality_score",
                0.5
            )

            # Calculate composite score
            composite_score = (
                normalized_score
                * (1.0 - settings.QUALITY_WEIGHT)
            ) + (
                quality_score
                * settings.QUALITY_WEIGHT
            )

            boosted_results.append(
                {
                    "chunk": candidate,
                    "score": round(
                        composite_score,
                        4
                    )
                }
            )

        # Sort by composite score
        boosted_results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        # --------------------------------------------------------
        # 6. FORMAT SEARCH RESULTS
        # --------------------------------------------------------

        results = []

        for idx, item in enumerate(
            boosted_results[:top_k]
        ):

            chunk = item["chunk"]

            snippet = self._generate_snippet(
                chunk["text"],
                query
            )

            results.append(
                {
                    "rank": idx + 1,
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk.get("doc_id"),
                    "title": chunk.get("title", ""),
                    "url": chunk["url"],
                    "heading": chunk.get("heading", ""),
                    "snippet": snippet,
                    "score": item["score"],
                    "quality_score": chunk.get(
                        "metadata", {}
                    ).get(
                        "quality_score",
                        0.5
                    )
                }
            )

        return results

    # ============================================================
    # SEARCH SNIPPET GENERATION
    # ============================================================

    def _generate_snippet(
        self,
        text: str,
        query: str
    ) -> str:
        """
        Find the most relevant sentence or section
        containing query words.
        """

        sentences = re.split(
            r'(?<=[.!?])\s+',
            text
        )

        query_words = [
            word.lower()
            for word in query.split()
            if len(word) > 2
        ]

        if not query_words:

            return (
                text[:250] + "..."
                if len(text) > 250
                else text
            )

        best_sentence = ""
        max_matches = -1

        for sentence in sentences:

            matches = sum(
                1
                for word in query_words
                if word in sentence.lower()
            )

            if matches > max_matches:

                max_matches = matches
                best_sentence = sentence

        # Highlight query terms
        snippet = (
            best_sentence
            or sentences[0]
        )

        for word in query_words:

            pattern = re.compile(
                rf'\b({re.escape(word)})\b',
                re.IGNORECASE
            )

            snippet = pattern.sub(
                r'**\1**',
                snippet
            )

        if len(snippet) > 250:
            snippet = snippet[:250] + "..."

        return snippet

    # ============================================================
    # SAVE INDEXES
    # ============================================================

    def save(self, dir_path: str = None):
        """
        Save BM25 index and vector embeddings to disk.
        """

        path = (
            dir_path
            or str(settings.absolute_index_dir)
        )

        os.makedirs(
            path,
            exist_ok=True
        )

        # Save BM25 index
        self.bm25_index.save(path)

        # Save vector embeddings
        if self.embeddings.size > 0:

            emb_path = os.path.join(
                path,
                "vector_index.npy"
            )

            try:

                np.save(
                    emb_path,
                    self.embeddings
                )

                logger.info(
                    f"Saved vector embeddings to {emb_path}"
                )

            except Exception as e:

                logger.error(
                    f"Failed to save embeddings: {e}"
                )

    # ============================================================
    # LOAD INDEXES
    # ============================================================

    def load(self, dir_path: str = None) -> bool:
        """
        Load BM25 and vector indexes.

        Validate that saved vector embeddings match
        the number of BM25 document chunks.
        """

        path = (
            dir_path
            or str(settings.absolute_index_dir)
        )

        # Load BM25 index
        bm25_success = self.bm25_index.load(path)

        # Load vector embeddings
        emb_path = os.path.join(
            path,
            "vector_index.npy"
        )

        embeddings_success = False

        # Reset embeddings before loading
        self.embeddings = np.empty((0, 0))

        if os.path.exists(emb_path):

            try:

                loaded_embeddings = np.load(
                    emb_path,
                    allow_pickle=False
                )

                # Validate saved index consistency
                if (
                    loaded_embeddings.ndim != 2
                    or loaded_embeddings.shape[0]
                    != len(self.bm25_index.chunks)
                    or loaded_embeddings.shape[1] == 0
                ):

                    raise ValueError(
                        "Stored vector index does not "
                        "match BM25 chunk count."
                    )

                self.embeddings = loaded_embeddings

                logger.info(
                    f"Loaded vector embeddings with "
                    f"shape {self.embeddings.shape}"
                )

                embeddings_success = True

            except Exception as e:

                logger.error(
                    f"Failed to load embeddings: {e}"
                )

                self.embeddings = np.empty((0, 0))

        return bm25_success and embeddings_success