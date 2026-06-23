from __future__ import annotations

from .models import SearchDocument, stable_id
from .text import normalize_text, split_sentences


def chunk_text(
    *,
    title: str,
    content: str,
    url: str,
    source: str,
    published_at: str,
    category: str = "在线正文片段",
    tags: list[str] | None = None,
    max_chars: int = 900,
    overlap_sentences: int = 1,
) -> list[SearchDocument]:
    text = normalize_text(content)
    if not text:
        return []

    sentences = split_sentences(text)
    if not sentences:
        sentences = [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        sentence = normalize_text(sentence)
        if not sentence:
            continue
        if current and current_len + len(sentence) > max_chars:
            chunks.append(" ".join(current))
            current = current[-overlap_sentences:] if overlap_sentences else []
            current_len = sum(len(item) for item in current)
        current.append(sentence)
        current_len += len(sentence)
    if current:
        chunks.append(" ".join(current))

    base_tags = list(tags or [])
    if "body-read" not in base_tags:
        base_tags.append("body-read")

    documents: list[SearchDocument] = []
    for index, chunk in enumerate(chunks[:8], start=1):
        documents.append(
            SearchDocument(
                id=stable_id("chunk", url, title, str(index), chunk[:80]),
                title=f"{title} · 正文片段 {index}",
                content=chunk,
                url=url,
                source=source,
                published_at=published_at,
                category=category,
                tags=base_tags + [f"chunk:{index}"],
            )
        )
    return documents
