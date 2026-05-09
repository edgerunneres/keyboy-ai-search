from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha1
from typing import Any


def stable_id(*parts: str) -> str:
    joined = "::".join(part.strip() for part in parts if part)
    return sha1(joined.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class SearchDocument:
    title: str
    content: str
    url: str
    source: str
    published_at: str
    category: str = "综合"
    tags: list[str] = field(default_factory=list)
    id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchDocument":
        doc = cls(
            title=str(data.get("title", "")).strip(),
            content=str(data.get("content", "")).strip(),
            url=str(data.get("url", "")).strip(),
            source=str(data.get("source", "")).strip() or "本地知识库",
            published_at=str(data.get("published_at", "")).strip() or "2026-01-01",
            category=str(data.get("category", "综合")).strip() or "综合",
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
            id=str(data.get("id", "")).strip(),
        )
        if not doc.id:
            doc.id = stable_id(doc.url, doc.title, doc.content[:80])
        return doc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentTrace:
    name: str
    status: str
    message: str
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchHit:
    document: SearchDocument
    score: float
    snippet: str
    explanation: str
    score_parts: dict[str, float]
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "score": round(self.score, 4),
            "snippet": self.snippet,
            "explanation": self.explanation,
            "score_parts": {key: round(value, 4) for key, value in self.score_parts.items()},
            "matched_terms": self.matched_terms,
        }


@dataclass(slots=True)
class SearchResponse:
    query: str
    mode: str
    hits: list[SearchHit]
    summary: str
    insights: list[str]
    query_profile: dict[str, Any]
    metrics: dict[str, Any]
    traces: list[AgentTrace]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "hits": [hit.to_dict() for hit in self.hits],
            "summary": self.summary,
            "insights": self.insights,
            "query_profile": self.query_profile,
            "metrics": self.metrics,
            "traces": [trace.to_dict() for trace in self.traces],
        }

