from __future__ import annotations

import re
import urllib.parse
import urllib.request

from .text import normalize_text
from .web_reader import SourceReadResult


GITHUB_RE = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s#?]+)(?:/(.*))?$", re.I)


def is_github_url(url: str) -> bool:
    return bool(GITHUB_RE.match(url))


def _read_url(url: str, *, timeout: float, user_agent: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(1_500_000).decode("utf-8", errors="ignore")


def read_github(url: str, *, timeout: float = 8.0, user_agent: str = "KeyBoySourceReader/1.1") -> SourceReadResult:
    match = GITHUB_RE.match(url)
    if not match:
        return SourceReadResult(url=url, title=url, text="", source_type="github", status="unsupported", risks=["不是 GitHub 仓库链接。"])

    owner, repo, path = match.groups()
    repo = repo.removesuffix(".git")
    candidates: list[str] = []
    if path and path.startswith("blob/"):
        parts = path.split("/", 2)
        if len(parts) == 3:
            branch = parts[1]
            file_path = parts[2]
            candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}")
    for branch in ("main", "master"):
        candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md")
        candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.zh-CN.md")

    last_error = ""
    for candidate in candidates:
        try:
            text = _read_url(candidate, timeout=timeout, user_agent=user_agent)
            text = normalize_text(_strip_markdown_noise(text))
            if len(text) >= 120:
                title = f"{owner}/{repo} README"
                return SourceReadResult(
                    url=url,
                    title=title,
                    text=text,
                    source_type="github",
                    status="ok",
                    risks=[],
                    metadata={"raw_url": candidate},
                )
        except Exception as exc:
            last_error = str(exc)

    return SourceReadResult(
        url=url,
        title=f"{owner}/{repo}",
        text="",
        source_type="github",
        status="failed",
        risks=[f"GitHub README 未能读取：{last_error or '无可用 README'}"],
    )


def _strip_markdown_noise(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^[#>*\-\s]+", "", text, flags=re.M)
    return urllib.parse.unquote(text)
