from __future__ import annotations

from collections import Counter

from .models import SearchHit
from .text import split_sentences, tokenize


def build_summary(query: str, hits: list[SearchHit], max_sentences: int = 4) -> tuple[str, list[str]]:
    if not hits:
        return "未找到足够相关的资料。建议换用更具体的课程、算法、模块或质量指标关键词。", []

    query_terms = set(tokenize(query))
    scored_sentences: list[tuple[float, str, str]] = []
    source_counter: Counter[str] = Counter()

    for hit_index, hit in enumerate(hits[:6]):
        source_counter[hit.document.source] += 1
        for pos, sentence in enumerate(split_sentences(hit.document.content)[:8]):
            terms = set(tokenize(sentence))
            coverage = len(query_terms & terms) / max(1, len(query_terms))
            density = len(terms & set(hit.matched_terms)) / max(1, len(terms))
            score = 0.52 * coverage + 0.28 * density + 0.12 * (1 / (1 + hit_index)) + 0.08 * (1 / (1 + pos))
            if score > 0:
                scored_sentences.append((score, sentence, hit.document.source))

    selected: list[str] = []
    seen = set()
    for _, sentence, source in sorted(scored_sentences, key=lambda item: item[0], reverse=True):
        normalized = sentence[:42]
        if normalized in seen:
            continue
        seen.add(normalized)
        selected.append(f"{sentence}（来源：{source}）")
        if len(selected) >= max_sentences:
            break

    if not selected:
        top = hits[0].document
        selected.append(f"最相关资料为《{top.title}》，建议优先查看其摘要与评分解释。（来源：{top.source}）")

    insights = [
        f"Top-{min(len(hits), 6)} 结果覆盖 {len(source_counter)} 个来源，最高分 {hits[0].score:.1f}。",
        f"主导排序因素：{hits[0].explanation}。",
    ]
    if len(hits) >= 3:
        categories = sorted({hit.document.category for hit in hits[:5]})
        insights.append("相关主题分布：" + "、".join(categories) + "。")

    return " ".join(selected), insights

