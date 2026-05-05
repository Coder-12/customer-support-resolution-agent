from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import CHROMA_DIR, COLLECTION_NAME, VECTOR_STORE_MODE


@dataclass
class RetrievedChunk:
    text: str
    metadata: dict[str, Any]
    score: float


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", text.lower()) if len(token) > 2}


def _model_cache_available(model_name: str) -> bool:
    model_key = model_name.replace("/", "--")
    candidates = [
        Path(os.getenv("HF_HOME", "")) / "hub" / f"models--{model_key}" if os.getenv("HF_HOME") else None,
        Path.home() / ".cache" / "huggingface" / "hub" / f"models--{model_key}",
    ]
    return any(path is not None and path.exists() for path in candidates)


class _LocalFallbackStore:
    """Dependency-light fallback used only when ChromaDB is not installed.

    The production/intended path is ChromaDB + sentence-transformers. This fallback keeps
    the CLI/evals runnable in constrained environments while preserving the same interface.
    """

    def __init__(self, collection_name: str):
        self.path = Path(CHROMA_DIR) / f"{collection_name}_fallback.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows: list[dict[str, Any]] = []
        if self.path.exists():
            self.rows = json.loads(self.path.read_text(encoding="utf-8"))

    def reset(self) -> None:
        self.rows = []
        self.path.write_text("[]", encoding="utf-8")

    def add_chunks(self, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.rows = [
            {"id": item_id, "text": text, "metadata": metadata}
            for item_id, text, metadata in zip(ids, texts, metadatas)
        ]
        self.path.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")

    def query(self, query_text: str, k: int = 5, where: dict[str, Any] | None = None) -> list[RetrievedChunk]:
        q = _tokens(query_text)
        scored: list[RetrievedChunk] = []
        for row in self.rows:
            metadata = row["metadata"]
            if where and any(metadata.get(key) != value for key, value in where.items()):
                continue
            d = _tokens(row["text"] + " " + " ".join(str(v) for v in metadata.values()))
            if not q or not d:
                score = 0.0
            else:
                score = len(q & d) / math.sqrt(len(q) * len(d))
            if score > 0:
                scored.append(RetrievedChunk(text=row["text"], metadata=metadata, score=round(score, 4)))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:k]


class ChromaVectorStore:
    """Thin vector-store wrapper.

    Primary implementation: ChromaDB persistent vector store with sentence-transformer embeddings.
    Fallback implementation: local lexical store when ChromaDB is unavailable.
    """

    def __init__(self, collection_name: str = COLLECTION_NAME):
        self.collection_name = collection_name
        model_name = "sentence-transformers/all-MiniLM-L6-v2"
        if VECTOR_STORE_MODE == "fallback":
            self._mode = "fallback"
            self.fallback = _LocalFallbackStore(collection_name)
            return
        if VECTOR_STORE_MODE == "auto" and not _model_cache_available(model_name):
            self._mode = "fallback"
            self.fallback = _LocalFallbackStore(collection_name)
            return
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            self._mode = "chroma"
            self.embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=model_name
            )
            self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            self.fallback = None
        except Exception:
            if VECTOR_STORE_MODE == "chroma":
                raise
            self._mode = "fallback"
            self.fallback = _LocalFallbackStore(collection_name)

    @property
    def mode(self) -> str:
        return self._mode

    def reset(self) -> None:
        if self._mode == "fallback":
            assert self.fallback is not None
            self.fallback.reset()
            return
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection.name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        if not ids:
            return
        if self._mode == "fallback":
            assert self.fallback is not None
            self.fallback.add_chunks(ids, texts, metadatas)
            return
        self.collection.add(ids=ids, documents=texts, metadatas=metadatas)

    def query(self, query_text: str, k: int = 5, where: dict[str, Any] | None = None) -> list[RetrievedChunk]:
        if self._mode == "fallback":
            assert self.fallback is not None
            return self.fallback.query(query_text, k=k, where=where)
        result = self.collection.query(query_texts=[query_text], n_results=k, where=where)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks: list[RetrievedChunk] = []
        for doc, meta, distance in zip(docs, metas, distances):
            score = max(0.0, 1.0 - float(distance))
            chunks.append(RetrievedChunk(text=doc, metadata=meta or {}, score=score))
        return chunks
