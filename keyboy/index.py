from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from .models import SearchDocument, SearchHit
from .text import cosine, hashed_vector, make_snippet, normalize_text, tokenize


class HybridSearchIndex:
    def __init__(self) -> None:
        self.documents: list[SearchDocument] = []
        self.doc_tokens: dict[str, Counter[str]] = {}
        self.title_tokens: dict[str, set[str]] = {}
        self.doc_lengths: dict[str, int] = {}
        self.doc_freq: Counter[str] = Counter()
        self.idf: dict[str, float] = {}
        self.vectors: dict[str, list[float]] = {}
        self.avg_doc_length = 1.0
        self.sources: list[str] = []
        self.categories: list[str] = []

    def build(self, documents: list[SearchDocument]) -> None:
        self.documents = documents
        self.doc_tokens.clear()
        self.title_tokens.clear()
        self.doc_lengths.clear()
        self.doc_freq.clear()
        self.vectors.clear()

        for doc in documents:
            combined = f"{doc.title} {' '.join(doc.tags)} {doc.content}"
            tokens = Counter(tokenize(combined))
            self.doc_tokens[doc.id] = tokens
            self.title_tokens[doc.id] = set(tokenize(doc.title))
            self.doc_lengths[doc.id] = sum(tokens.values()) or 1
            self.vectors[doc.id] = hashed_vector(combined)
            for token in tokens:
                self.doc_freq[token] += 1

        total = max(1, len(documents))
        self.avg_doc_length = sum(self.doc_lengths.values()) / total if documents else 1.0
        self.idf = {
            token: math.log(1.0 + (total - freq + 0.5) / (freq + 0.5))
            for token, freq in self.doc_freq.items()
        }
        self.sources = sorted({doc.source for doc in documents})
        self.categories = sorted({doc.category for doc in documents})

    def query_profile(self, query: str) -> dict[str, Any]:
        terms = tokenize(query)
        has_question = any(mark in query for mark in ("?", "？", "如何", "为什么", "怎样", "对比"))
        technical_hits = sum(1 for term in ("bm25", "rrf", "tf-idf", "ndcg", "api") if term in query.lower())
        semantic_weight = 0.44
        if len(query) >= 18 or has_question:
            semantic_weight += 0.16
        if technical_hits >= 1 or len(terms) <= 3:
            semantic_weight -= 0.10
        semantic_weight = max(0.28, min(0.68, semantic_weight))
        lexical_weight = 1.0 - semantic_weight
        return {
            "tokens": terms,
            "token_count": len(terms),
            "has_question_intent": has_question,
            "technical_hits": technical_hits,
            "lexical_weight": round(lexical_weight, 3),
            "semantic_weight": round(semantic_weight, 3),
        }

    def stats(self) -> dict[str, Any]:
        total_tokens = sum(self.doc_lengths.values())
        return {
            "documents": len(self.documents),
            "sources": self.sources,
            "categories": self.categories,
            "vocabulary": len(self.doc_freq),
            "avg_doc_length": round(self.avg_doc_length, 2),
            "tokens": total_tokens,
        }

    def _allowed_docs(self, source: str | None = None, category: str | None = None) -> list[SearchDocument]:
        allowed = self.documents
        if source:
            allowed = [doc for doc in allowed if doc.source == source]
        if category:
            allowed = [doc for doc in allowed if doc.category == category]
        return allowed

    def _bm25_scores(self, query_terms: list[str], allowed: list[SearchDocument]) -> dict[str, float]:
        k1 = 1.45
        b = 0.72
        scores: dict[str, float] = defaultdict(float)
        for doc in allowed:
            tokens = self.doc_tokens.get(doc.id, Counter())
            length = self.doc_lengths.get(doc.id, 1)
            for term in query_terms:
                tf = tokens.get(term, 0)
                if tf <= 0:
                    continue
                idf = self.idf.get(term, 0.0)
                denominator = tf + k1 * (1 - b + b * length / self.avg_doc_length)
                scores[doc.id] += idf * tf * (k1 + 1) / denominator
                if term in self.title_tokens.get(doc.id, set()):
                    scores[doc.id] += 0.32 * idf
        return dict(scores)

    def _semantic_scores(self, query: str, allowed: list[SearchDocument]) -> dict[str, float]:
        query_vector = hashed_vector(query)
        return {doc.id: max(0.0, cosine(query_vector, self.vectors.get(doc.id, []))) for doc in allowed}

    @staticmethod
    def _rank(scores: dict[str, float]) -> list[str]:
        return [doc_id for doc_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0]

    @staticmethod
    def _normalize(scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        max_score = max(scores.values()) or 1.0
        return {key: value / max_score for key, value in scores.items()}

    def _rrf(
        self,
        rankings: list[tuple[list[str], float]],
        rank_constant: int = 60,
    ) -> dict[str, float]:
        fused: dict[str, float] = defaultdict(float)
        for ranking, weight in rankings:
            for rank, doc_id in enumerate(ranking, start=1):
                fused[doc_id] += weight / (rank_constant + rank)
        return dict(fused)

    @staticmethod
    def _date_score(value: str) -> float:
        try:
            year = datetime.fromisoformat(value).year
        except ValueError:
            return 0.45
        if year >= 2026:
            return 1.0
        if year == 2025:
            return 0.82
        if year == 2024:
            return 0.66
        return 0.48

    def search(
        self,
        query: str,
        *,
        mode: str = "hybrid",
        source: str | None = None,
        category: str | None = None,
        limit: int = 8,
    ) -> tuple[list[SearchHit], dict[str, Any]]:
        query = normalize_text(query)
        profile = self.query_profile(query)
        query_terms = profile["tokens"]
        allowed = self._allowed_docs(source=source, category=category)
        if not query_terms:
            return [], profile

        bm25_raw = self._bm25_scores(query_terms, allowed)
        semantic_raw = self._semantic_scores(query, allowed)
        bm25_norm = self._normalize(bm25_raw)
        semantic_norm = self._normalize(semantic_raw)
        lexical_rank = self._rank(bm25_raw)
        semantic_rank = self._rank(semantic_raw)

        if mode == "lexical":
            fused = bm25_norm
        elif mode == "semantic":
            fused = semantic_norm
        else:
            fused = self._rrf(
                [
                    (lexical_rank, float(profile["lexical_weight"])),
                    (semantic_rank, float(profile["semantic_weight"])),
                ]
            )
            fused = self._normalize(fused)

        scored: list[tuple[SearchDocument, float, dict[str, float], list[str]]] = []
        for doc in allowed:
            base = fused.get(doc.id, 0.0)
            if base <= 0:
                continue
            matched_terms = [term for term in query_terms if term in self.doc_tokens.get(doc.id, {})]
            title_coverage = len(set(matched_terms) & self.title_tokens.get(doc.id, set())) / max(1, len(set(query_terms)))
            content_coverage = len(set(matched_terms)) / max(1, len(set(query_terms)))
            rerank = 0.46 * title_coverage + 0.34 * content_coverage + 0.20 * self._date_score(doc.published_at)
            final = 100.0 * (0.78 * base + 0.22 * rerank)
            scored.append(
                (
                    doc,
                    final,
                    {
                        "bm25": bm25_norm.get(doc.id, 0.0) * 100,
                        "semantic": semantic_norm.get(doc.id, 0.0) * 100,
                        "rrf": base * 100,
                        "rerank": rerank * 100,
                    },
                    matched_terms,
                )
            )

        scored.sort(key=lambda item: item[1], reverse=True)
        hits: list[SearchHit] = []
        for doc, score, parts, matched_terms in scored[: max(1, min(limit, 20))]:
            snippet = make_snippet(doc.content, matched_terms or query_terms)
            reason_bits = []
            if parts["bm25"] >= 55:
                reason_bits.append("关键词匹配强")
            if parts["semantic"] >= 55:
                reason_bits.append("语义相似度高")
            if matched_terms and set(matched_terms) & self.title_tokens.get(doc.id, set()):
                reason_bits.append("标题命中核心词")
            if not reason_bits:
                reason_bits.append("综合排序进入 Top-K")
            hits.append(
                SearchHit(
                    document=doc,
                    score=score,
                    snippet=snippet,
                    explanation="、".join(reason_bits),
                    score_parts=parts,
                    matched_terms=matched_terms[:10],
                )
            )
        return hits, profile

