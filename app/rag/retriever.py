from __future__ import annotations

from app.agent.schemas import EvidenceItem
from app.rag.vector_store import ChromaVectorStore


class DocumentationRetriever:
    def __init__(self):
        self.store = ChromaVectorStore()

    def retrieve(self, queries: list[str], product_area: str | None = None, k_per_query: int = 3) -> list[EvidenceItem]:
        seen: set[tuple[str, str, int]] = set()
        evidence: list[EvidenceItem] = []
        where = {"product_area": product_area} if product_area and product_area != "general" else None
        for query in queries:
            chunks = self.store.query(query, k=k_per_query, where=where)
            if not chunks and where is not None:
                chunks = self.store.query(query, k=k_per_query)
            for chunk in chunks:
                key = (
                    chunk.metadata.get("source", ""),
                    chunk.metadata.get("section", ""),
                    int(chunk.metadata.get("chunk_index", 0)),
                )
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(EvidenceItem(
                    source=chunk.metadata.get("source", "unknown"),
                    source_type="doc",
                    title=chunk.metadata.get("title"),
                    content=chunk.text,
                    score=round(chunk.score, 4),
                    metadata=chunk.metadata,
                ))
        evidence.sort(key=lambda item: item.score or 0, reverse=True)
        return evidence[:6]


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "refund approved but not received"
    retriever = DocumentationRetriever()
    for item in retriever.retrieve([query], k_per_query=5):
        print(f"[{item.score}] {item.source} / {item.metadata.get('section')}: {item.content[:180]}...")
