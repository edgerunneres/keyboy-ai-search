from __future__ import annotations

import re
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .chunker import chunk_text
from .github_reader import is_github_url, read_github
from .models import SearchDocument, stable_id
from .pdf_reader import looks_like_pdf, read_pdf
from .text import normalize_text
from .web_reader import SourceReadResult, read_web_page


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


@dataclass
class SourceReadSummary:
    documents: list[SearchDocument] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return len(self.reports)

    @property
    def readable(self) -> int:
        return sum(1 for item in self.reports if item.get("status") in {"ok", "partial"})


class SourceReader:
    def __init__(self, *, timeout: float = 8.0, max_sources: int = 10) -> None:
        self.timeout = timeout
        self.max_sources = max_sources
        self.user_agent = "KeyBoySourceReader/1.1 (course-design local test)"

    def read_documents(
        self,
        documents: list[SearchDocument],
        *,
        on_progress: Any = None,
        should_cancel: Any = None,
    ) -> SourceReadSummary:
        summary = SourceReadSummary()
        seen_urls: set[str] = set()
        readable_candidates = []
        for doc in documents:
            url = self._normalize_url(doc.url)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            readable_candidates.append((doc, url))
            if len(readable_candidates) >= self.max_sources:
                break

        for doc, url in readable_candidates:
            if should_cancel and should_cancel():
                break
            if on_progress:
                on_progress(f"读取来源正文: {doc.title[:36]}")
            report = self._read_one(doc, url)
            summary.reports.append(report)
            summary.warnings.extend(report.get("risks") or [])
            if report.get("text"):
                chunks = chunk_text(
                    title=report.get("title") or doc.title,
                    content=report["text"],
                    url=url,
                    source=doc.source,
                    published_at=doc.published_at,
                    tags=list({*doc.tags, "source-read", f"read:{report.get('source_type', 'web')}", f"read-status:{report.get('status', 'ok')}"}),
                )
                summary.documents.extend(chunks)
        return summary

    def _read_one(self, doc: SearchDocument, url: str) -> dict[str, Any]:
        try:
            result = self._dispatch_read(url)
            text = normalize_text(result.text)
            risks = list(result.risks)
            if len(text) < 300:
                prefix = f"《{result.title or doc.title}》" if (result.title or doc.title) else f"链接 {url}"
                risks.append(f"{prefix} 正文提取过短（可能防爬或仅为摘要），信息可能偏弱")
            return {
                "document_id": doc.id,
                "url": url,
                "title": result.title or doc.title,
                "source": doc.source,
                "source_type": result.source_type,
                "status": result.status,
                "text": text,
                "length": len(text),
                "risks": risks,
                "metadata": result.metadata,
            }
        except urllib.error.HTTPError as exc:
            return self._failed_report(doc, url, f"链接不可访问 HTTP {exc.code}")
        except urllib.error.URLError as exc:
            return self._failed_report(doc, url, f"链接不可访问：{getattr(exc, 'reason', exc)}")
        except TimeoutError:
            return self._failed_report(doc, url, "来源读取超时")
        except Exception as exc:
            return self._failed_report(doc, url, f"来源读取失败：{exc}")

    def _dispatch_read(self, url: str) -> SourceReadResult:
        if is_github_url(url):
            return read_github(url, timeout=self.timeout, user_agent=self.user_agent)
        if looks_like_pdf(url):
            return read_pdf(url, timeout=self.timeout, user_agent=self.user_agent)
        return read_web_page(url, timeout=self.timeout, user_agent=self.user_agent)

    def _failed_report(doc: SearchDocument, url: str, reason: str) -> dict[str, Any]:
        prefix = f"《{doc.title}》" if doc.title else f"链接 {url}"
        return {
            "document_id": doc.id,
            "url": url,
            "title": doc.title,
            "source": doc.source,
            "source_type": "unknown",
            "status": "failed",
            "text": "",
            "length": 0,
            "risks": [f"{prefix} {reason}"],
            "metadata": {},
        }

    @staticmethod
    def _normalize_url(url: str) -> str:
        value = normalize_text(url)
        if not value:
            return ""
        doi = DOI_RE.search(value)
        if doi and not value.lower().startswith("http"):
            return f"https://doi.org/{doi.group(0)}"
        if value.startswith("doi:"):
            return f"https://doi.org/{value[4:].strip()}"
        if value.startswith("http://") or value.startswith("https://"):
            return value
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme and parsed.netloc:
            return value
        return ""


def source_identity(doc: SearchDocument) -> str:
    title = normalize_text(doc.title).lower()
    url = normalize_text(doc.url).lower()
    doi = DOI_RE.search(url)
    if doi:
        return f"doi:{doi.group(0).lower()}"
    if url:
        parsed = urllib.parse.urlparse(url)
        clean_path = parsed.path.rstrip("/")
        return f"url:{parsed.netloc}{clean_path}"
    return stable_id(title[:160], doc.source)
