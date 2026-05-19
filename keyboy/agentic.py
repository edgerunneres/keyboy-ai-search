from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .agents import CleanAgent, IndexAgent, traced
from .index import HybridSearchIndex
from .llm import LLMProvider
from .models import AgentTrace, SearchDocument
from .online_sources import OnlineSourceClient
from .storage import load_documents
from .summarizer import build_summary
from .text import split_sentences, tokenize


@dataclass
class ResearchPlan:
    intent: str
    subqueries: list[str]
    source_plan: list[str]
    required_evidence: list[str]
    llm_used: bool = False


@dataclass
class ResearchResult:
    query: str
    answer: str
    plan: ResearchPlan
    citations: list[dict[str, Any]]
    findings: list[str]
    risks: list[str]
    metrics: dict[str, Any]
    traces: list[AgentTrace]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "plan": {
                "intent": self.plan.intent,
                "subqueries": self.plan.subqueries,
                "source_plan": self.plan.source_plan,
                "required_evidence": self.plan.required_evidence,
                "llm_used": self.plan.llm_used,
            },
            "citations": self.citations,
            "findings": self.findings,
            "risks": self.risks,
            "metrics": self.metrics,
            "traces": [trace.to_dict() for trace in self.traces],
        }


class ResearchPlannerAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @traced("ResearchPlannerAgent")
    def plan(self, query: str) -> Any:
        fallback = self._fallback_plan(query)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research planning agent for an online LLM multi-agent search system. "
                    "Return strict JSON with intent, subqueries, source_plan, required_evidence."
                ),
            },
            {"role": "user", "content": query},
        ]
        parsed, llm_result = self.llm.chat_json(messages, fallback=fallback.__dict__)
        plan = ResearchPlan(
            intent=str(parsed.get("intent") or fallback.intent),
            subqueries=[str(x) for x in parsed.get("subqueries", fallback.subqueries)][:6],
            source_plan=[str(x).lower() for x in parsed.get("source_plan", fallback.source_plan)][:4],
            required_evidence=[str(x) for x in parsed.get("required_evidence", fallback.required_evidence)][:6],
            llm_used=llm_result.used_remote_model,
        )
        return type("AgentResult", (), {"payload": plan, "trace_message": f"规划 {len(plan.subqueries)} 个子查询"})()

    @staticmethod
    def _fallback_plan(query: str) -> ResearchPlan:
        terms = " ".join(tokenize(query)[:8]) or query
        subqueries = [
            query,
            f"{query} survey benchmark architecture",
            f"{terms} agentic RAG multi-agent",
            f"{terms} GraphRAG LightRAG Self-RAG",
        ]
        return ResearchPlan(
            intent="在线研究与证据合成",
            subqueries=subqueries,
            source_plan=["openalex", "semanticscholar", "arxiv", "crossref"],
            required_evidence=["最新论文", "高引用研究", "开源项目/框架", "可落地架构"],
            llm_used=False,
        )


class OnlineDiscoveryAgent:
    def __init__(self, client: OnlineSourceClient | None = None) -> None:
        self.client = client or OnlineSourceClient()

    @traced("OnlineDiscoveryAgent")
    def discover(self, plan: ResearchPlan, *, online: bool = True) -> Any:
        if not online:
            return type("AgentResult", (), {"payload": ([], ["online=false"]), "trace_message": "跳过在线源"})()
        docs: list[SearchDocument] = []
        warnings: list[str] = []
        for subquery in plan.subqueries[:4]:
            found, source_warnings = self.client.search(subquery, plan.source_plan)
            docs.extend(found)
            warnings.extend(source_warnings)
        unique: dict[str, SearchDocument] = {}
        for doc in docs:
            unique.setdefault(doc.id, doc)
        return type("AgentResult", (), {"payload": (list(unique.values()), warnings), "trace_message": f"在线发现 {len(unique)} 篇资料"})()


class EvidenceRankerAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @traced("EvidenceRankerAgent")
    def rank(self, index: HybridSearchIndex, query: str, *, limit: int = 10) -> Any:
        hits, profile = index.search(query, mode="hybrid", limit=limit)
        return type("AgentResult", (), {"payload": {"hits": hits, "profile": profile}, "trace_message": f"证据排序 {len(hits)} 条"})()


class SynthesisAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @traced("SynthesisAgent")
    def synthesize(self, query: str, hits) -> Any:
        citations = []
        context_blocks = []
        for idx, hit in enumerate(hits[:8], start=1):
            sentences = split_sentences(hit.document.content)
            evidence = sentences[0] if sentences else hit.document.content[:240]
            citations.append(
                {
                    "id": idx,
                    "title": hit.document.title,
                    "source": hit.document.source,
                    "url": hit.document.url,
                    "published_at": hit.document.published_at,
                    "score": round(hit.score, 2),
                    "evidence": evidence,
                }
            )
            context_blocks.append(f"[{idx}] {hit.document.title}\n{evidence}\nURL: {hit.document.url}")

        fallback_summary, fallback_findings = build_summary(query, hits)
        fallback_answer = f"{fallback_summary}\n\n证据来源：" + "、".join(f"[{c['id']}] {c['title']}" for c in citations[:5])
        if not citations:
            fallback_answer = "未获得足够证据。建议开启在线源或提供更具体的问题。"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a citation-grounded synthesis agent. Answer in Chinese. "
                    "Use only the provided evidence, cite sources like [1], [2], and state uncertainty."
                ),
            },
            {"role": "user", "content": f"问题：{query}\n\n证据：\n" + "\n\n".join(context_blocks)},
        ]
        llm_result = self.llm.chat(messages, temperature=0.2, max_tokens=1500)
        answer = llm_result.text if llm_result.used_remote_model else fallback_answer
        payload = {
            "answer": answer,
            "citations": citations,
            "findings": fallback_findings,
            "llm_used": llm_result.used_remote_model,
            "model": llm_result.model,
        }
        return type("AgentResult", (), {"payload": payload, "trace_message": "完成证据合成"})()


class CriticAgent:
    @traced("CriticAgent")
    def critique(self, result: dict[str, Any]) -> Any:
        citations = result.get("citations", [])
        risks: list[str] = []
        if not result.get("llm_used"):
            risks.append("当前未检测到大模型 API Key，回答由本地确定性合成器生成；设置 KEYBOY_LLM_API_KEY 和 KEYBOY_LLM_MODEL 后会启用真实 LLM。")
        if len(citations) < 3:
            risks.append("证据数量不足，建议扩大在线源或增加子查询。")
        sources = {item.get("source") for item in citations}
        if len(sources) < 2 and citations:
            risks.append("来源多样性不足，建议引入更多数据库或网页源。")
        if not risks:
            risks.append("证据数量与来源多样性达到当前演示阈值。")
        return type("AgentResult", (), {"payload": risks, "trace_message": f"输出 {len(risks)} 条校验意见"})()


@dataclass
class AgenticKeyBoySystem:
    llm: LLMProvider = field(default_factory=LLMProvider)
    clean_agent: CleanAgent = field(default_factory=CleanAgent)
    index_agent: IndexAgent = field(default_factory=IndexAgent)
    planner_agent: ResearchPlannerAgent = field(init=False)
    discovery_agent: OnlineDiscoveryAgent = field(default_factory=OnlineDiscoveryAgent)
    ranker_agent: EvidenceRankerAgent = field(init=False)
    synthesis_agent: SynthesisAgent = field(init=False)
    critic_agent: CriticAgent = field(default_factory=CriticAgent)

    def __post_init__(self) -> None:
        self.planner_agent = ResearchPlannerAgent(self.llm)
        self.ranker_agent = EvidenceRankerAgent(self.llm)
        self.synthesis_agent = SynthesisAgent(self.llm)

    def research(self, query: str, *, online: bool = True, include_local: bool = True, limit: int = 10) -> ResearchResult:
        traces: list[AgentTrace] = []
        started = time.perf_counter()

        plan_result, trace = self.planner_agent.plan(query)
        traces.append(trace)
        plan: ResearchPlan = plan_result.payload

        discovery_result, trace = self.discovery_agent.discover(plan, online=online)
        traces.append(trace)
        online_docs, source_warnings = discovery_result.payload
        documents = list(online_docs)
        if include_local:
            documents.extend(load_documents())

        clean_result, trace = self.clean_agent.clean(documents)
        traces.append(trace)
        cleaned = clean_result.payload if clean_result else []

        index_result, trace = self.index_agent.build(cleaned)
        traces.append(trace)
        index = index_result.payload if index_result else HybridSearchIndex()

        rank_result, trace = self.ranker_agent.rank(index, query, limit=limit)
        traces.append(trace)
        ranked = rank_result.payload if rank_result else {"hits": [], "profile": {}}
        hits = ranked["hits"]

        synth_result, trace = self.synthesis_agent.synthesize(query, hits)
        traces.append(trace)
        synth = synth_result.payload if synth_result else {"answer": "", "citations": [], "findings": [], "llm_used": False, "model": ""}

        critique_result, trace = self.critic_agent.critique(synth)
        traces.append(trace)
        risks = list(source_warnings[:4]) + (critique_result.payload if critique_result else [])

        latency_ms = (time.perf_counter() - started) * 1000
        metrics = {
            "latency_ms": round(latency_ms, 2),
            "online_documents": len(online_docs),
            "indexed_documents": len(cleaned),
            "result_count": len(hits),
            "llm_used": bool(synth.get("llm_used")),
            "llm_model": synth.get("model") or "deterministic-fallback",
            "query_profile": ranked.get("profile", {}),
            "index": index.stats(),
        }
        return ResearchResult(
            query=query,
            answer=synth["answer"],
            plan=plan,
            citations=synth["citations"],
            findings=synth["findings"],
            risks=risks,
            metrics=metrics,
            traces=traces,
        )

