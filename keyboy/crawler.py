from __future__ import annotations

import time
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

from .models import SearchDocument, stable_id
from .text import normalize_text


class ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = normalize_text(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif len(text) > 8:
            self.text_parts.append(text)

    def document(self, url: str) -> SearchDocument:
        parsed = urllib.parse.urlparse(url)
        title = normalize_text(" ".join(self.title_parts)) or parsed.netloc
        content = normalize_text(" ".join(self.text_parts))
        return SearchDocument(
            id=stable_id(url, title),
            title=title[:120],
            content=content,
            url=url,
            source=parsed.netloc,
            published_at="2026-05-09",
            category="在线爬取",
            tags=["crawler", "live"],
        )


class PoliteCrawler:
    def __init__(self, user_agent: str = "KeyBoyCourseDesign/2.0", delay_seconds: float = 0.8) -> None:
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds

    def _robots_allows(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            return True
        return parser.can_fetch(self.user_agent, url)

    def fetch(self, url: str, timeout: int = 8) -> SearchDocument | None:
        if not self._robots_allows(url):
            return None
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None
            raw = response.read(1_500_000)
        parser = ReadableHTMLParser()
        parser.feed(raw.decode("utf-8", errors="ignore"))
        time.sleep(self.delay_seconds)
        doc = parser.document(url)
        return doc if len(doc.content) >= 120 else None

