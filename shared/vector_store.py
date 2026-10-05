"""
Artilery Shared Vector Store — ChromaDB + Bedrock Embeddings.

Provides a VectorStore class for embedding, storing, and searching documents
using ChromaDB as the local vector database and AWS Bedrock Titan for embeddings.

Collections:
    - event_logs: All Kafka events stored as text
    - deployment_logs: CodeDeploy log text chunks
    - jira_comments: Jira ticket comments and descriptions

Usage:
    from shared.vector_store import VectorStore
    vs = VectorStore()
    vs.embed_and_store("doc-1", "Some text", {"service": "PaymentService"})
    results = vs.similarity_search("payment failure", k=5)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.vector_store")

# Default collections
COLLECTIONS = ["event_logs", "deployment_logs", "jira_comments"]

# Chunking defaults
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


class VectorStore:
    """ChromaDB vector store with AWS Bedrock Titan embeddings."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "event_logs",
    ) -> None:
        settings = get_settings()
        self._persist_dir = persist_directory or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), ".chromadb"
        )
        self._collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None
        self._embed_fn: Any = None

    def _get_client(self) -> Any:
        """Initialize ChromaDB client (lazy)."""
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=self._persist_dir)
            logger.info("VECTOR | ChromaDB initialized | dir=%s", self._persist_dir)
        return self._client

    def _get_collection(self) -> Any:
        """Get or create the ChromaDB collection."""
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "VECTOR | Collection ready | name=%s | count=%d",
                self._collection_name,
                self._collection.count(),
            )
        return self._collection

    def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding using AWS Bedrock Titan Embeddings."""
        settings = get_settings()

        try:
            import boto3

            bedrock = boto3.client(
                "bedrock-runtime",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )

            body = json.dumps({"inputText": text[:8000]})  # Titan limit

            response = bedrock.invoke_model(
                modelId="amazon.titan-embed-text-v1",
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            return result["embedding"]

        except Exception as exc:
            logger.warning("VECTOR | Bedrock embedding failed, using hash fallback | error=%s", exc)
            return self._hash_embedding(text)

    @staticmethod
    def _hash_embedding(text: str, dim: int = 1536) -> list[float]:
        """Deterministic hash-based fallback embedding (for when Bedrock is unavailable)."""
        h = hashlib.sha512(text.encode("utf-8")).digest()
        # Expand hash to fill dimension
        expanded = h * ((dim * 4 // len(h)) + 1)
        import struct

        values = struct.unpack(f"{dim}f", expanded[: dim * 4])
        # Normalize
        magnitude = max(sum(v * v for v in values) ** 0.5, 1e-10)
        return [v / magnitude for v in values]

    # ── Public API ───────────────────────────────────────────────────────

    def embed_and_store(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Embed text using Bedrock Titan and store in ChromaDB.

        Args:
            doc_id: Unique document identifier.
            text: Text content to embed.
            metadata: Optional metadata dict (values must be str/int/float/bool).
        """
        collection = self._get_collection()
        embedding = self._get_embedding(text)

        # ChromaDB requires metadata values to be str/int/float/bool
        clean_meta = {}
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)

        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[clean_meta] if clean_meta else None,
        )
        logger.info("VECTOR | Document stored | id=%s | collection=%s", doc_id, self._collection_name)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents using query embedding.

        Args:
            query: Search query text.
            k: Number of results to return.
            filter: Optional ChromaDB where filter.

        Returns:
            List of {text, metadata, score} dicts, ordered by relevance.
        """
        collection = self._get_collection()

        if collection.count() == 0:
            logger.info("VECTOR | Collection empty, returning no results")
            return []

        query_embedding = self._get_embedding(query)

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(k, collection.count()),
        }
        if filter:
            kwargs["where"] = filter

        try:
            results = collection.query(**kwargs)
        except Exception as exc:
            logger.warning("VECTOR | Search failed | error=%s", exc)
            return []

        output: list[dict[str, Any]] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc in enumerate(documents):
            output.append({
                "text": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "score": 1.0 - (distances[i] if i < len(distances) else 0.0),
            })

        return output

    def delete(self, doc_id: str) -> None:
        """Delete a document by ID."""
        collection = self._get_collection()
        try:
            collection.delete(ids=[doc_id])
            logger.info("VECTOR | Document deleted | id=%s", doc_id)
        except Exception as exc:
            logger.warning("VECTOR | Delete failed | id=%s | error=%s", doc_id, exc)

    def clear_collection(self, collection_name: Optional[str] = None) -> None:
        """Clear all documents from a collection."""
        name = collection_name or self._collection_name
        client = self._get_client()
        try:
            client.delete_collection(name)
            self._collection = None
            logger.info("VECTOR | Collection cleared | name=%s", name)
        except Exception as exc:
            logger.warning("VECTOR | Clear failed | name=%s | error=%s", name, exc)

    def get_count(self) -> int:
        """Return number of documents in the collection."""
        return self._get_collection().count()


def initialize_collections() -> None:
    """Initialize all default ChromaDB collections on startup."""
    for collection_name in COLLECTIONS:
        vs = VectorStore(collection_name=collection_name)
        vs._get_collection()
        logger.info("VECTOR | Collection initialized | name=%s | count=%d", collection_name, vs.get_count())


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for embedding.

    Args:
        text: Input text to chunk.
        chunk_size: Maximum characters per chunk.
        overlap: Number of overlapping characters between chunks.

    Returns:
        List of text chunks.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap

    return chunks
