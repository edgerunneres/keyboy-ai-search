from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from .models import SearchDocument, stable_id
from .text import normalize_text


ABSTRACT_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class OnlinePaper:
    title: str
    abstract: str
    url: str
    source: str
    published_at: str
    authors: list[str]
    citation_count: int = 0
    venue: str = ""

    def to_document(self) -> SearchDocument:
        author_text = "、".join(self.authors[:5])
        citation = f"引用数：{self.citation_count}。" if self.citation_count else ""
        venue = f"发表位置：{self.venue}。" if self.venue else ""
        content = normalize_text(f"{self.abstract} {venue}{citation} 作者：{author_text}")
        return SearchDocument(
            id=stable_id(self.source, self.url, self.title),
            title=self.title[:180],
            content=content or self.title,
            url=self.url,
            source=self.source,
            published_at=self.published_at,
            category="在线研究资料",
            tags=["online", self.source],
        )


class OnlineSourceClient:
    def __init__(self, timeout: float = 6.0, per_source_limit: int = 4) -> None:
        self.timeout = timeout
        self.per_source_limit = per_source_limit
        self.user_agent = "KeyBoyAgenticResearch/3.0 (course-design; polite online research)"
        self.disabled = os.getenv("KEYBOY_DISABLE_ONLINE", "0") == "1"

    def search(self, query: str, sources: list[str] | None = None) -> tuple[list[SearchDocument], list[str]]:
        if self.disabled:
            return [], ["Online source access disabled by KEYBOY_DISABLE_ONLINE=1."]
        selected = sources or ["openalex", "semanticscholar", "arxiv", "crossref"]
        documents: list[SearchDocument] = []
        warnings: list[str] = []
        for source in selected:
            try:
                if source == "openalex":
                    papers = self._openalex(query)
                elif source == "semanticscholar":
                    papers = self._semantic_scholar(query)
                elif source == "arxiv":
                    papers = self._arxiv(query)
                elif source == "crossref":
                    papers = self._crossref(query)
                else:
                    papers = []
                documents.extend(paper.to_document() for paper in papers)
                time.sleep(0.15)
            except Exception as exc:
                warnings.append(f"{source} failed: {exc}")

        unique: dict[str, SearchDocument] = {}
        for doc in documents:
            unique.setdefault(doc.id, doc)
        return list(unique.values()), warnings

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {"User-Agent": self.user_agent}
        if "semanticscholar.org" in url and os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
            headers["x-api-key"] = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", errors="ignore")

    @staticmethod
    def _year_to_date(year: Any) -> str:
        try:
            return f"{int(year)}-01-01"
        except (TypeError, ValueError):
            return "2026-01-01"

    @staticmethod
    def _strip_abstract(value: Any) -> str:
        text = " ".join(value) if isinstance(value, list) else str(value or "")
        return normalize_text(html.unescape(ABSTRACT_TAG_RE.sub(" ", text)))

    def _openalex(self, query: str) -> list[OnlinePaper]:
        params = urllib.parse.urlencode(
            {
                "search": query,
                "per-page": self.per_source_limit,
                "sort": "relevance_score:desc",
                "mailto": "course-design@example.com",
            }
        )
        data = self._get_json(f"https://api.openalex.org/works?{params}")
        papers: list[OnlinePaper] = []
        for item in data.get("results", []):
            title = normalize_text(item.get("display_name") or "")
            abstract = self._invert_openalex_abstract(item.get("abstract_inverted_index") or {})
            authors = [
                normalize_text(auth.get("author", {}).get("display_name", ""))
                for auth in item.get("authorships", [])
                if auth.get("author", {}).get("display_name")
            ]
            url = item.get("doi") or item.get("id") or ""
            if title:
                papers.append(
                    OnlinePaper(
                        title=title,
                        abstract=abstract,
                        url=url,
                        source="OpenAlex",
                        published_at=self._year_to_date(item.get("publication_year")),
                        authors=authors,
                        citation_count=int(item.get("cited_by_count") or 0),
                        venue=self._openalex_venue(item),
                    )
                )
        return papers

    @staticmethod
    def _openalex_venue(item: dict[str, Any]) -> str:
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        return normalize_text(source.get("display_name") or "")

    @staticmethod
    def _invert_openalex_abstract(index: dict[str, list[int]]) -> str:
        if not index:
            return ""
        terms: list[tuple[int, str]] = []
        for word, positions in index.items():
            for pos in positions:
                terms.append((int(pos), word))
        return normalize_text(" ".join(word for _, word in sorted(terms)))

    def _semantic_scholar(self, query: str) -> list[OnlinePaper]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "limit": self.per_source_limit,
                "fields": "title,abstract,url,year,authors,venue,citationCount,isOpenAccess",
            }
        )
        data = self._get_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{params}")
        papers: list[OnlinePaper] = []
        for item in data.get("data", []):
            title = normalize_text(item.get("title") or "")
            if not title:
                continue
            papers.append(
                OnlinePaper(
                    title=title,
                    abstract=normalize_text(item.get("abstract") or ""),
                    url=item.get("url") or "",
                    source="Semantic Scholar",
                    published_at=self._year_to_date(item.get("year")),
                    authors=[normalize_text(a.get("name", "")) for a in item.get("authors", []) if a.get("name")],
                    citation_count=int(item.get("citationCount") or 0),
                    venue=normalize_text(item.get("venue") or ""),
                )
            )
        return papers

    def _arxiv(self, query: str) -> list[OnlinePaper]:
        params = urllib.parse.urlencode(
            {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": self.per_source_limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        text = self._get_text(f"https://export.arxiv.org/api/query?{params}")
        root = ET.fromstring(text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers: list[OnlinePaper] = []
        for entry in root.findall("atom:entry", ns):
            title = normalize_text(entry.findtext("atom:title", default="", namespaces=ns))
            abstract = normalize_text(entry.findtext("atom:summary", default="", namespaces=ns))
            url = normalize_text(entry.findtext("atom:id", default="", namespaces=ns))
            published = normalize_text(entry.findtext("atom:published", default="", namespaces=ns))[:10] or "2026-01-01"
            authors = [
                normalize_text(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ]
            if title:
                papers.append(OnlinePaper(title, abstract, url, "arXiv", published, authors, venue="arXiv"))
        return papers

    def _crossref(self, query: str) -> list[OnlinePaper]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "rows": self.per_source_limit,
                "select": "title,URL,abstract,issued,published-online,published-print,container-title,author,is-referenced-by-count",
            }
        )
        data = self._get_json(f"https://api.crossref.org/works?{params}")
        papers: list[OnlinePaper] = []
        for item in data.get("message", {}).get("items", []):
            title = normalize_text(" ".join(item.get("title") or []))
            date_parts = (
                item.get("published-online", {}).get("date-parts")
                or item.get("published-print", {}).get("date-parts")
                or item.get("issued", {}).get("date-parts")
                or [[2026]]
            )
            year = date_parts[0][0] if date_parts and date_parts[0] else 2026
            authors = [
                normalize_text(f"{a.get('given', '')} {a.get('family', '')}")
                for a in item.get("author", [])
                if a.get("family") or a.get("given")
            ]
            if title:
                papers.append(
                    OnlinePaper(
                        title=title,
                        abstract=self._strip_abstract(item.get("abstract", "")),
                        url=item.get("URL", ""),
                        source="Crossref",
                        published_at=self._year_to_date(year),
                        authors=authors,
                        citation_count=int(item.get("is-referenced-by-count") or 0),
                        venue=normalize_text(" ".join(item.get("container-title") or [])),
                    )
                )
        return papers
