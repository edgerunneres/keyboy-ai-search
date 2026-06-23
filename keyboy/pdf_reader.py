from __future__ import annotations

import re
import urllib.request

from .text import normalize_text
from .web_reader import SourceReadResult


PDF_TEXT_RE = re.compile(rb"\(([^()]{20,600})\)")


def looks_like_pdf(url: str) -> bool:
    return url.lower().split("?", 1)[0].endswith(".pdf")


def read_pdf(url: str, *, timeout: float = 8.0, user_agent: str = "KeyBoySourceReader/1.1") -> SourceReadResult:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(3_000_000)
    matches = []
    for match in PDF_TEXT_RE.finditer(raw):
        try:
            text = match.group(1).decode("utf-8", errors="ignore")
        except UnicodeDecodeError:
            text = match.group(1).decode("latin-1", errors="ignore")
        text = normalize_text(text)
        if len(text) >= 30:
            matches.append(text)
    text = normalize_text(" ".join(matches[:40]))
    risks = ["PDF 使用轻量解析器读取，复杂排版可能缺失。"]
    status = "partial"
    if len(text) < 300:
        risks.append("PDF 未能提取足够正文，当前仅确认链接可访问。")
        status = "metadata-only"
    return SourceReadResult(url=url, title=url, text=text, source_type="pdf", status=status, risks=risks)
