from __future__ import annotations

import html
import math
import re
from collections import Counter
from hashlib import blake2b
from typing import Iterable


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.#/-]*|[\u4e00-\u9fff]+")
SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.])\s+")
SPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")

STOPWORDS = {
    "的",
    "了",
    "和",
    "与",
    "是",
    "在",
    "对",
    "为",
    "及",
    "中",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "a",
    "an",
}

DOMAIN_TERMS = [
    "软件工程",
    "搜索引擎",
    "混合检索",
    "语义检索",
    "向量检索",
    "倒排索引",
    "多智能体",
    "可解释",
    "智能摘要",
    "课程设计",
    "需求分析",
    "概要设计",
    "详细设计",
    "质量保证",
    "配置管理",
    "自动评测",
    "召回率",
    "相关性",
    "reciprocal rank fusion",
    "rrf",
    "bm25",
    "tf-idf",
    "ndcg",
    "api",
]


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = TAG_RE.sub(" ", value)
    value = value.replace("\u3000", " ")
    return SPACE_RE.sub(" ", value).strip()


def _cjk_ngrams(text: str, min_n: int = 2, max_n: int = 3) -> Iterable[str]:
    if not text:
        return []
    for n in range(min_n, max_n + 1):
        if len(text) < n:
            continue
        for idx in range(len(text) - n + 1):
            gram = text[idx : idx + n]
            if any(ch not in STOPWORDS for ch in gram):
                yield gram


def tokenize(value: str) -> list[str]:
    value = normalize_text(value).lower()
    tokens: list[str] = []
    for term in DOMAIN_TERMS:
        if term in value:
            tokens.append(term)

    for match in TOKEN_RE.finditer(value):
        part = match.group(0).lower()
        if not part or part in STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            tokens.extend(ch for ch in part if ch not in STOPWORDS)
            tokens.extend(_cjk_ngrams(part))
        else:
            tokens.append(part)
    return tokens


def semantic_features(value: str) -> list[str]:
    text = normalize_text(value).lower()
    features = tokenize(text)
    compact = re.sub(r"\s+", "", text)
    for n in (3, 4, 5):
        for idx in range(max(0, len(compact) - n + 1)):
            gram = compact[idx : idx + n]
            if gram:
                features.append(f"char:{gram}")
    return features


def hashed_vector(value: str, dims: int = 384) -> list[float]:
    vector = [0.0] * dims
    counts = Counter(semantic_features(value))
    for token, count in counts.items():
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign * (1.0 + math.log1p(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def split_sentences(value: str) -> list[str]:
    text = normalize_text(value)
    parts = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
    return [part for part in parts if len(part) >= 8]


def fingerprint(value: str) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text[:500]


def make_snippet(content: str, query_terms: list[str], max_chars: int = 180) -> str:
    text = normalize_text(content)
    lowered = text.lower()
    positions = [lowered.find(term.lower()) for term in query_terms if term and lowered.find(term.lower()) >= 0]
    start = max(0, min(positions) - 55) if positions else 0
    snippet = text[start : start + max_chars]
    if start > 0:
        snippet = "..." + snippet
    if start + max_chars < len(text):
        snippet += "..."

    terms: list[str] = []
    for term in sorted(set(query_terms), key=len, reverse=True):
        if len(term) < 2:
            continue
        if any(term.lower() in existing.lower() for existing in terms):
            continue
        terms.append(term)
        if len(terms) >= 8:
            break
    if not terms:
        return html.escape(snippet)

    pattern = re.compile("|".join(re.escape(term) for term in terms), flags=re.IGNORECASE)
    output: list[str] = []
    cursor = 0
    for match in pattern.finditer(snippet):
        output.append(html.escape(snippet[cursor : match.start()]))
        output.append(f"<mark>{html.escape(match.group(0))}</mark>")
        cursor = match.end()
    output.append(html.escape(snippet[cursor:]))
    return "".join(output)
