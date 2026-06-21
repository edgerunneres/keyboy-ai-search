from __future__ import annotations

import html
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from .models import SearchDocument, stable_id
from .text import normalize_text


ABSTRACT_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
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


DISPLAY_NAMES = {
    "openalex": "OpenAlex",
    "semanticscholar": "Semantic Scholar",
    "arxiv": "arXiv",
    "crossref": "Crossref",
    "duckduckgo": "DuckDuckGo",
}


class OnlineSourceClient:
    def __init__(self, timeout: float = 15.0, per_source_limit: int = 5) -> None:
        self.timeout = float(os.getenv("KEYBOY_ONLINE_TIMEOUT", str(timeout)))
        self.per_source_limit = per_source_limit
        self.user_agent = "KeyBoyAgenticResearch/3.0 (course-design; polite online research)"
        self.disabled = os.getenv("KEYBOY_DISABLE_ONLINE", "0") == "1"
        self.semantic_scholar_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        self.openalex_api_key = os.getenv("OPENALEX_API_KEY", "")
        self.openalex_mailto = os.getenv("OPENALEX_MAILTO") or "yup300737@gmail.com"
        self.crossref_mailto = os.getenv("CROSSREF_MAILTO") or "yup300737@gmail.com"

    def configure(
        self,
        *,
        semantic_scholar_api_key: str | None = None,
        openalex_api_key: str | None = None,
        openalex_mailto: str | None = None,
        crossref_mailto: str | None = None,
        timeout: float | None = None,
        per_source_limit: int | None = None,
    ) -> None:
        if semantic_scholar_api_key is not None:
            self.semantic_scholar_api_key = semantic_scholar_api_key.strip()
        if openalex_api_key is not None:
            self.openalex_api_key = openalex_api_key.strip() or os.getenv("OPENALEX_API_KEY", "")
        if openalex_mailto is not None:
            self.openalex_mailto = openalex_mailto.strip()
        if crossref_mailto is not None:
            self.crossref_mailto = crossref_mailto.strip()
        if timeout is not None:
            self.timeout = max(3.0, float(timeout))
        if per_source_limit is not None:
            self.per_source_limit = max(1, min(8, int(per_source_limit)))

    def safe_config(self) -> dict[str, Any]:
        return {
            "semantic_scholar": {"has_api_key": bool(self.semantic_scholar_api_key)},
            "openalex": {
                "has_api_key": bool(self.openalex_api_key),
                "mailto": self.openalex_mailto,
            },
            "crossref": {"mailto": self.crossref_mailto},
            "timeout": self.timeout,
            "per_source_limit": self.per_source_limit,
        }

    def search(self, query: str, sources: list[str] | None = None, on_progress: Any = None) -> tuple[list[SearchDocument], list[str]]:
        if self.disabled:
            return [], ["Online source access disabled by KEYBOY_DISABLE_ONLINE=1."]
        selected = [source for source in (sources or []) if source in DISPLAY_NAMES]
        if not selected:
            selected = ["openalex", "semanticscholar", "arxiv", "crossref", "duckduckgo"]
        documents: list[SearchDocument] = []
        warnings: list[str] = []
        with ThreadPoolExecutor(max_workers=min(4, len(selected))) as executor:
            futures = {executor.submit(self._search_source, source, query): source for source in selected}
            for future in as_completed(futures):
                source = futures[future]
                if on_progress:
                    on_progress(f"发现在线资料: '{query}' -> 已返回 {DISPLAY_NAMES.get(source, source)}")
                try:
                    papers = future.result()
                    documents.extend(paper.to_document() for paper in papers)
                    time.sleep(0.05)
                except urllib.error.HTTPError as exc:
                    warnings.append(self._http_warning(source, exc))
                except (TimeoutError, socket.timeout):
                    warnings.append(f"{DISPLAY_NAMES.get(source, source)} 超时")
                except urllib.error.URLError as exc:
                    reason = str(getattr(exc, "reason", exc))
                    if "timed out" in reason.lower():
                        warnings.append(f"{DISPLAY_NAMES.get(source, source)} 超时")
                    else:
                        warnings.append(f"{DISPLAY_NAMES.get(source, source)} 暂不可用")
                except Exception:
                    warnings.append(f"{DISPLAY_NAMES.get(source, source)} 暂不可用")

        unique: dict[str, SearchDocument] = {}
        for doc in documents:
            unique.setdefault(doc.id, doc)
        return list(unique.values()), warnings

    def _search_source(self, source: str, query: str) -> list[OnlinePaper]:
        if source == "openalex":
            return self._openalex(query)
        if source == "semanticscholar":
            return self._semantic_scholar(query)
        if source == "arxiv":
            return self._arxiv(query)
        if source == "crossref":
            return self._crossref(query)
        if source == "duckduckgo":
            return self._duckduckgo(query)
        return []

    @staticmethod
    def _http_warning(source: str, exc: urllib.error.HTTPError) -> str:
        name = DISPLAY_NAMES.get(source, source)
        if exc.code == 429:
            return f"{name} 限流 429"
        if exc.code in {401, 403}:
            return f"{name} 拒绝访问 {exc.code}"
        return f"{name} HTTP {exc.code}"

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {"User-Agent": self.user_agent}
        if "semanticscholar.org" in url and self.semantic_scholar_api_key:
            headers["x-api-key"] = self.semantic_scholar_api_key
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
        query_params = {
            "search": query,
            "per-page": self.per_source_limit,
            "sort": "relevance_score:desc",
        }
        if self.openalex_mailto:
            query_params["mailto"] = self.openalex_mailto
        if self.openalex_api_key:
            query_params["api_key"] = self.openalex_api_key
        params = urllib.parse.urlencode(query_params)
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

    def _duckduckgo(self, query: str) -> list[OnlinePaper]:
        params = urllib.parse.urlencode({"q": query})
        url = f"https://html.duckduckgo.com/html/?{params}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                html_text = response.read().decode("utf-8", errors="ignore")
        except Exception:
            return []

        papers: list[OnlinePaper] = []
        pattern = re.compile(
            r'<a class="result__url" href="([^"]+)".*?'
            r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>.*?'
            r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )
        for match in pattern.finditer(html_text):
            if len(papers) >= self.per_source_limit:
                break
            url_str = urllib.parse.unquote(match.group(1).strip())
            if url_str.startswith("//"):
                url_str = "https:" + url_str
            elif url_str.startswith("/"):
                url_str = "https://duckduckgo.com" + url_str

            title = self._strip_abstract(match.group(2).strip())
            snippet = self._strip_abstract(match.group(3).strip())
            papers.append(
                OnlinePaper(
                    title=title,
                    abstract=snippet,
                    url=url_str,
                    source="duckduckgo",
                    published_at=self._year_to_date(2024),
                    authors=["Web Search"],
                    citation_count=0,
                    venue="Web"
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
        query_params = {
            "query": query,
            "rows": self.per_source_limit,
            "select": "title,URL,abstract,issued,published-online,published-print,container-title,author,is-referenced-by-count",
        }
        if self.crossref_mailto:
            query_params["mailto"] = self.crossref_mailto
        params = urllib.parse.urlencode(query_params)
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
