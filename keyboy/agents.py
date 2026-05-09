from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .crawler import PoliteCrawler
from .evaluator import evaluate
from .index import HybridSearchIndex
from .models import AgentTrace, SearchDocument, SearchResponse
from .storage import load_documents, load_eval_queries
from .summarizer import build_summary
from .text import fingerprint, normalize_text


def traced(name: str):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                message = getattr(result, "trace_message", None) or "完成"
                status = "ok"
            except Exception as exc:
                result = None
                message = f"失败：{exc}"
                status = "error"
            duration_ms = (time.perf_counter() - start) * 1000
            return result, AgentTrace(name=name, status=status, message=message, duration_ms=duration_ms)

        return wrapper

    return decorator


@dataclass
class AgentResult:
    payload: Any
    trace_message: str = "完成"


class CrawlAgent:
    @traced("CrawlAgent")
    def load(self, urls: list[str] | None = None) -> AgentResult:
        documents = load_documents()
        if urls:
            crawler = PoliteCrawler()
            for url in urls:
                doc = crawler.fetch(url)
                if doc:
                    documents.append(doc)
        return AgentResult(documents, f"载入 {len(documents)} 篇资料")


class CleanAgent:
    @traced("CleanAgent")
    def clean(self, documents: list[SearchDocument]) -> AgentResult:
        cleaned: list[SearchDocument] = []
        seen: set[str] = set()
        for doc in documents:
            doc.title = normalize_text(doc.title)
            doc.content = normalize_text(doc.content)
            key = fingerprint(doc.title + doc.content)
            if not doc.title or len(doc.content) < 60 or key in seen:
                continue
            seen.add(key)
            cleaned.append(doc)
        return AgentResult(cleaned, f"清洗去重后保留 {len(cleaned)} 篇")


class IndexAgent:
    @traced("IndexAgent")
    def build(self, documents: list[SearchDocument]) -> AgentResult:
        index = HybridSearchIndex()
        index.build(documents)
        return AgentResult(index, f"索引 {len(documents)} 篇，词表 {len(index.doc_freq)} 项")


class SearchAgent:
    @traced("SearchAgent")
    def search(self, index: HybridSearchIndex, query: str, options: dict[str, Any]) -> AgentResult:
        hits, profile = index.search(
            query,
            mode=options.get("mode", "hybrid"),
            source=options.get("source") or None,
            category=options.get("category") or None,
            limit=int(options.get("limit", 8)),
        )
        return AgentResult({"hits": hits, "profile": profile}, f"返回 {len(hits)} 条候选结果")


class InsightAgent:
    @traced("InsightAgent")
    def summarize(self, query: str, hits) -> AgentResult:
        summary, insights = build_summary(query, hits)
        return AgentResult({"summary": summary, "insights": insights}, "生成查询摘要与洞察")


class EvalAgent:
    @traced("EvalAgent")
    def evaluate(self, index: HybridSearchIndex) -> AgentResult:
        metrics = evaluate(index, load_eval_queries())
        return AgentResult(metrics, f"评测 {metrics.get('cases', 0)} 个查询")


@dataclass
class KeyBoySystem:
    crawl_agent: CrawlAgent = field(default_factory=CrawlAgent)
    clean_agent: CleanAgent = field(default_factory=CleanAgent)
    index_agent: IndexAgent = field(default_factory=IndexAgent)
    search_agent: SearchAgent = field(default_factory=SearchAgent)
    insight_agent: InsightAgent = field(default_factory=InsightAgent)
    eval_agent: EvalAgent = field(default_factory=EvalAgent)
    index: HybridSearchIndex | None = None
    traces: list[AgentTrace] = field(default_factory=list)
    eval_metrics: dict[str, Any] = field(default_factory=dict)

    def bootstrap(self, urls: list[str] | None = None) -> list[AgentTrace]:
        self.traces = []
        crawl_result, trace = self.crawl_agent.load(urls)
        self.traces.append(trace)
        documents = crawl_result.payload if crawl_result else []

        clean_result, trace = self.clean_agent.clean(documents)
        self.traces.append(trace)
        cleaned = clean_result.payload if clean_result else []

        index_result, trace = self.index_agent.build(cleaned)
        self.traces.append(trace)
        self.index = index_result.payload if index_result else HybridSearchIndex()

        eval_result, trace = self.eval_agent.evaluate(self.index)
        self.traces.append(trace)
        self.eval_metrics = eval_result.payload if eval_result else {}
        return self.traces

    def ensure_ready(self) -> None:
        if self.index is None:
            self.bootstrap()

    def search(self, query: str, **options: Any) -> SearchResponse:
        self.ensure_ready()
        assert self.index is not None
        traces = []
        start = time.perf_counter()

        search_result, trace = self.search_agent.search(self.index, query, options)
        traces.append(trace)
        payload = search_result.payload if search_result else {"hits": [], "profile": {}}
        hits = payload["hits"]

        insight_result, trace = self.insight_agent.summarize(query, hits)
        traces.append(trace)
        insight_payload = insight_result.payload if insight_result else {"summary": "", "insights": []}

        latency_ms = (time.perf_counter() - start) * 1000
        metrics = {
            "latency_ms": round(latency_ms, 2),
            "result_count": len(hits),
            "index": self.index.stats(),
            "evaluation": self.eval_metrics,
        }
        return SearchResponse(
            query=query,
            mode=options.get("mode", "hybrid"),
            hits=hits,
            summary=insight_payload["summary"],
            insights=insight_payload["insights"],
            query_profile=payload["profile"],
            metrics=metrics,
            traces=traces,
        )

