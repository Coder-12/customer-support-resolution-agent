from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.config import DOCS_DIR
from app.rag.vector_store import ChromaVectorStore


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    metadata: dict[str, Any] = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, body.strip()


def split_markdown_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = "Overview"
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("#"):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = re.sub(r"^#+\s*", "", line).strip() or "Untitled"
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return [(h, c) for h, c in sections if c]


def chunk_text(text: str, max_words: int = 140, overlap_words: int = 25) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(0, end - overlap_words)
    return chunks


def load_doc_chunks(docs_dir: Path = DOCS_DIR) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for path in sorted(docs_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        base_meta, body = parse_frontmatter(raw)
        for section, section_text in split_markdown_sections(body):
            for idx, chunk in enumerate(chunk_text(section_text)):
                chunk_id = hashlib.sha1(f"{path.name}:{section}:{idx}:{chunk}".encode()).hexdigest()
                ids.append(chunk_id)
                texts.append(chunk)
                metadatas.append({
                    "source": path.name,
                    "title": base_meta.get("title", path.stem),
                    "doc_type": base_meta.get("doc_type", "doc"),
                    "product_area": base_meta.get("product_area", "general"),
                    "updated_at": base_meta.get("updated_at", "unknown"),
                    "section": section,
                    "chunk_index": idx,
                })
    return ids, texts, metadatas


def ingest(reset: bool = True) -> int:
    store = ChromaVectorStore()
    if reset:
        store.reset()
    ids, texts, metadatas = load_doc_chunks()
    store.add_chunks(ids, texts, metadatas)
    return len(ids)


if __name__ == "__main__":
    count = ingest(reset=True)
    print(f"Indexed {count} documentation chunks from {DOCS_DIR}")
