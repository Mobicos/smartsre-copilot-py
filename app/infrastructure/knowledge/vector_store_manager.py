"""Vector store manager with Milvus and pgvector backends."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Protocol

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_milvus import Milvus
from loguru import logger
from sqlalchemy import text

from app.core.config import AppSettings
from app.core.milvus_client import milvus_manager
from app.platform.persistence.database import get_engine

COLLECTION_NAME = "biz"


class VectorStoreBackend(Protocol):
    backend_name: str

    @property
    def is_initialized(self) -> bool: ...

    def add_documents(self, documents: list[Document]) -> list[str]: ...

    def delete_by_source(self, file_path: str) -> int: ...

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        *,
        collection_name: str | None = None,
        score_threshold: float = 0.0,
    ) -> list[Document]: ...

    def health_check(self) -> bool: ...


class DegradedVectorStoreAdapter:
    """No-op vector backend used when the configured store is unavailable."""

    def __init__(self, *, backend_name: str) -> None:
        self.backend_name = backend_name

    @property
    def is_initialized(self) -> bool:
        return False

    def add_documents(self, documents: list[Document]) -> list[str]:
        logger.warning(
            f"Vector store is degraded; skipped indexing {len(documents)} document chunks"
        )
        return []

    def delete_by_source(self, file_path: str) -> int:
        logger.warning(f"Vector store is degraded; skipped delete for source {file_path}")
        return 0

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        *,
        collection_name: str | None = None,
        score_threshold: float = 0.0,
    ) -> list[Document]:
        logger.warning(f"Vector store is degraded; returning empty search results for k={k}")
        return []

    def health_check(self) -> bool:
        return False


class VectorStoreManager:
    """Facade over the configured vector-store backend."""

    def __init__(self, embedding_service: Embeddings, settings: AppSettings | None = None):
        self.embedding_service = embedding_service
        settings = settings or AppSettings.from_env()
        backend = settings.vector_store_backend.strip().lower()
        try:
            if backend == "pgvector":
                self._backend: VectorStoreBackend = PgVectorStoreAdapter(
                    embedding_service=embedding_service,
                    collection_name=settings.pgvector_collection_name,
                )
            else:
                self._backend = MilvusVectorStoreAdapter(
                    embedding_service=embedding_service, settings=settings
                )
        except Exception as exc:
            logger.warning(f"Vector store backend '{backend}' degraded during init: {exc}")
            self._backend = DegradedVectorStoreAdapter(backend_name=f"{backend}_degraded")

    @property
    def backend_name(self) -> str:
        return self._backend.backend_name

    @property
    def is_initialized(self) -> bool:
        return self._backend.is_initialized

    def add_documents(self, documents: list[Document]) -> list[str]:
        return self._backend.add_documents(documents)

    def delete_by_source(self, file_path: str) -> int:
        return self._backend.delete_by_source(file_path)

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        *,
        collection_name: str | None = None,
        score_threshold: float | None = None,
        settings: AppSettings | None = None,
    ) -> list[Document]:
        settings = settings or AppSettings.from_env()
        threshold = score_threshold if score_threshold is not None else settings.rag_score_threshold
        return self._backend.similarity_search(
            query, k=k, collection_name=collection_name, score_threshold=threshold
        )

    def health_check(self) -> bool:
        return self._backend.health_check()


class MilvusVectorStoreAdapter:
    """Milvus-backed vector store."""

    backend_name = "milvus"

    def __init__(self, embedding_service: Embeddings, settings: AppSettings | None = None):
        self.embedding_service = embedding_service
        self._settings = settings or AppSettings.from_env()
        self.vector_store: Milvus | None = None
        self.collection_name = COLLECTION_NAME
        self._initialize_vector_store()

    @property
    def is_initialized(self) -> bool:
        return self.vector_store is not None

    def _initialize_vector_store(self) -> None:
        if self.vector_store is not None:
            return

        try:
            _ = milvus_manager.connect()
            connection_args = {
                "uri": f"http://{self._settings.milvus_host}:{self._settings.milvus_port}",
            }
            self.vector_store = Milvus(
                embedding_function=self.embedding_service,
                collection_name=self.collection_name,
                connection_args=connection_args,
                auto_id=False,
                drop_old=False,
                text_field="content",
                vector_field="vector",
                primary_field="id",
                metadata_field="metadata",
            )
            logger.info(
                f"Milvus VectorStore initialized: {self._settings.milvus_host}:{self._settings.milvus_port}, "
                f"collection={self.collection_name}"
            )
        except Exception as exc:
            logger.warning(f"Milvus VectorStore initialization degraded: {exc}")
            raise

    def add_documents(self, documents: list[Document]) -> list[str]:
        try:
            self._initialize_vector_store()
            start_time = time.time()
            ids = [str(uuid.uuid4()) for _ in documents]
            result_ids = self.get_vector_store().add_documents(documents, ids=ids)
            elapsed = time.time() - start_time
            logger.info(f"Added {len(documents)} documents to Milvus in {elapsed:.2f}s")
            return result_ids
        except Exception as exc:
            logger.error(f"Adding documents to Milvus failed: {exc}")
            raise

    def delete_by_source(self, file_path: str) -> int:
        try:
            self._initialize_vector_store()
            collection = milvus_manager.get_collection()
            expr = f'metadata["_source"] == {_milvus_string_literal(file_path)}'
            result = collection.delete(expr)
            deleted_count = result.delete_count if hasattr(result, "delete_count") else 0
            logger.info(f"Deleted {deleted_count} Milvus chunks for source {file_path}")
            return int(deleted_count)
        except Exception as exc:
            logger.warning(f"Deleting Milvus chunks for source failed: {exc}")
            return 0

    def get_vector_store(self) -> Milvus:
        self._initialize_vector_store()
        if self.vector_store is None:
            raise RuntimeError("VectorStore is not initialized")
        return self.vector_store

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        *,
        collection_name: str | None = None,
        score_threshold: float = 0.0,
    ) -> list[Document]:
        try:
            store = self.get_vector_store()
            if collection_name:
                filter_expr = (
                    f'metadata["collection_name"] == {_milvus_string_literal(collection_name)}'
                )
                results = store.similarity_search_with_relevance_scores(
                    query, k=k, expr=filter_expr
                )
            else:
                results = store.similarity_search_with_relevance_scores(query, k=k)
            # Filter by score threshold
            return [doc for doc, score in results if score >= score_threshold]
        except Exception as exc:
            logger.error(f"Milvus similarity search failed: {exc}")
            return []

    def health_check(self) -> bool:
        try:
            self._initialize_vector_store()
            return self.vector_store is not None and milvus_manager.health_check()
        except Exception:
            return False


class PgVectorStoreAdapter:
    """PostgreSQL pgvector-backed vector store."""

    backend_name = "pgvector"

    def __init__(self, *, embedding_service: Embeddings, collection_name: str) -> None:
        self.embedding_service = embedding_service
        self.collection_name = collection_name
        self._initialized = False
        self._initialize_vector_store()

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def _initialize_vector_store(self) -> None:
        if self._initialized:
            return
        engine = get_engine()
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT to_regclass('public.knowledge_documents') AS documents_table,
                           to_regclass('public.knowledge_chunks') AS chunks_table
                    """
                    )
                )
                .mappings()
                .one()
            )
            if row["documents_table"] is None or row["chunks_table"] is None:
                raise RuntimeError("pgvector knowledge tables are missing; run Alembic migrations")
        self._initialized = True
        logger.info(f"pgvector VectorStore initialized: collection={self.collection_name}")

    def add_documents(self, documents: list[Document]) -> list[str]:
        try:
            self._initialize_vector_store()
        except Exception as exc:
            logger.warning(f"pgvector add degraded before write: {exc}")
            return []
        if not documents:
            return []

        contents = [document.page_content for document in documents]
        embeddings = self.embedding_service.embed_documents(contents)

        # Prepare batches: deduplicate documents (by source) and build chunk rows.
        doc_batch: dict[str, dict[str, Any]] = {}
        chunk_batch: list[dict[str, Any]] = []

        for document, embedding in zip(documents, embeddings, strict=True):
            chunk_id = str(uuid.uuid4())
            source = str(
                document.metadata.get("_source")
                or document.metadata.get("source")
                or document.metadata.get("file_path")
                or "unknown"
            )
            document_id = _document_id(source)
            metadata = _json_metadata(document.metadata)

            if document_id not in doc_batch:
                doc_batch[document_id] = {
                    "document_id": document_id,
                    "collection_name": self.collection_name,
                    "source": source,
                    "content": document.page_content,
                    "metadata": metadata,
                }

            chunk_batch.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "collection_name": self.collection_name,
                    "source": source,
                    "content": document.page_content,
                    "metadata": metadata,
                    "embedding": _vector_literal(embedding),
                }
            )

        engine = get_engine()
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO knowledge_documents (
                            document_id, collection_name, source, content, metadata
                        )
                        VALUES (
                            :document_id, :collection_name, :source, :content, CAST(:metadata AS jsonb)
                        )
                        ON CONFLICT (document_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            metadata = EXCLUDED.metadata
                        """
                    ),
                    list(doc_batch.values()),
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO knowledge_chunks (
                            chunk_id, document_id, collection_name, source, content, metadata, embedding
                        )
                        VALUES (
                            :chunk_id,
                            :document_id,
                            :collection_name,
                            :source,
                            :content,
                            CAST(:metadata AS jsonb),
                            CAST(:embedding AS vector)
                        )
                        """
                    ),
                    chunk_batch,
                )
        except Exception as exc:
            logger.warning(f"pgvector add degraded during write: {exc}")
            return []
        logger.info(
            f"Added {len(chunk_batch)} documents to pgvector collection={self.collection_name}"
        )
        return [c["chunk_id"] for c in chunk_batch]

    def delete_by_source(self, file_path: str) -> int:
        try:
            self._initialize_vector_store()
        except Exception as exc:
            logger.warning(f"pgvector delete degraded before write: {exc}")
            return 0
        engine = get_engine()
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    DELETE FROM knowledge_documents
                    WHERE collection_name = :collection_name AND source = :source
                    """
                ),
                {"collection_name": self.collection_name, "source": file_path},
            )
        deleted = int(result.rowcount or 0)
        logger.info(f"Deleted {deleted} pgvector documents for source {file_path}")
        return deleted

    def similarity_search(
        self,
        query: str,
        k: int = 3,
        *,
        collection_name: str | None = None,
        score_threshold: float = 0.0,
    ) -> list[Document]:
        try:
            self._initialize_vector_store()
            query_embedding = self.embedding_service.embed_query(query)
            effective_collection = collection_name or self.collection_name
            engine = get_engine()
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT content, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
                        FROM knowledge_chunks
                        WHERE collection_name = :collection_name
                        ORDER BY embedding <=> CAST(:embedding AS vector)
                        LIMIT :limit
                        """
                    ),
                    {
                        "collection_name": effective_collection,
                        "embedding": _vector_literal(query_embedding),
                        "limit": k,
                    },
                ).mappings()
                documents = []
                for row in rows:
                    score = float(row["score"])
                    if score < score_threshold:
                        continue
                    metadata = dict(row["metadata"] or {})
                    metadata["score"] = score
                    documents.append(Document(page_content=str(row["content"]), metadata=metadata))
                return documents
        except Exception as exc:
            logger.warning(f"pgvector search degraded: {exc}")
            return []

    def health_check(self) -> bool:
        try:
            self._initialize_vector_store()
            with get_engine().connect() as connection:
                row = connection.execute(text("SELECT 1")).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning(f"pgvector health check failed: {exc}")
            return False


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _milvus_string_literal(value: str) -> str:
    """Return a Milvus expression string literal with control characters escaped."""
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _json_metadata(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, ensure_ascii=False, default=str)


def _document_id(source: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, source))
