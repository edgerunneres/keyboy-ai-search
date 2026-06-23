from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from .text import normalize_text


SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript|svg|canvas|iframe)[^>]*>.*?</\1>", re.I | re.S)


@dataclass
class SourceReadResult:
    url: str
    title: str
    text: str
    source_type: str = "web"
    status: str = "ok"
    risks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_stack: list[str] = []
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg", "canvas", "iframe", "nav", "footer", "header"}:
            self.skip_stack.append(lowered)
        if lowered == "title":
            self.in_title = True
        if lowered in {"p", "br", "li", "h1", "h2", "h3", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self.skip_stack and self.skip_stack[-1] == lowered:
            self.skip_stack.pop()
        if lowered == "title":
            self.in_title = False
        if lowered in {"p", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return
        text = html.unescape(data)
        if self.in_title:
            self.title_parts.append(text)
            return
        if text.strip():
            self.parts.append(text)

    @property
    def title(self) -> str:
        return normalize_text(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        lines = []
        for line in " ".join(self.parts).splitlines():
            cleaned = normalize_text(line)
            if len(cleaned) >= 20:
                lines.append(cleaned)
        return normalize_text(" ".join(lines))


def read_web_page(url: str, *, timeout: float = 8.0, user_agent: str = "KeyBoySourceReader/1.1") -> SourceReadResult:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(2_000_000)
    if "pdf" in content_type.lower() or url.lower().split("?", 1)[0].endswith(".pdf"):
        return SourceReadResult(url=url, title=url, text="", source_type="pdf", status="unsupported", risks=["PDF 来源需要 PDF 读取器处理。"])

    html_text = raw.decode("utf-8", errors="ignore")
    html_text = SCRIPT_STYLE_RE.sub(" ", html_text)
    parser = ReadableHTMLParser()
    parser.feed(html_text)
    title = parser.title or url
    text = parser.text
    risks: list[str] = []
    status = "ok"
    if len(text) < 300:
        risks.append("网页正文较短，可能只读取到摘要或导航文本。")
        status = "partial"
    return SourceReadResult(url=url, title=title, text=text, source_type="web", status=status, risks=risks)
