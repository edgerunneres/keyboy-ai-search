from __future__ import annotations

import math
import time
from typing import Any

from .index import HybridSearchIndex


def _dcg(gains: list[int]) -> float:
    return sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))


def evaluate(index: HybridSearchIndex, cases: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    if not cases:
        return {"cases": 0, "recall_at_5": 0.0, "ndcg_at_5": 0.0, "avg_latency_ms": 0.0}

    recalls: list[float] = []
    ndcgs: list[float] = []
    latencies: list[float] = []

    title_to_id = {doc.title: doc.id for doc in index.documents}

    for case in cases:
        query = str(case.get("query", ""))
        relevant_titles = case.get("relevant_titles", [])
        relevant = {title_to_id[title] for title in relevant_titles if title in title_to_id}
        if not relevant:
            continue
        start = time.perf_counter()
        hits, _ = index.search(query, limit=k)
        latencies.append((time.perf_counter() - start) * 1000)
        returned = [hit.document.id for hit in hits[:k]]
        gains = [1 if doc_id in relevant else 0 for doc_id in returned]
        recalls.append(len(set(returned) & relevant) / len(relevant))
        ideal = [1] * min(len(relevant), k)
        ndcgs.append((_dcg(gains) / _dcg(ideal)) if ideal else 0.0)

    return {
        "cases": len(cases),
        "recall_at_5": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        "ndcg_at_5": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
    }

