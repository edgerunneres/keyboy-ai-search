from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .agents import CleanAgent, IndexAgent, traced
from .index import HybridSearchIndex
from .llm import LLMProvider
from .models import AgentTrace, SearchDocument
from .online_sources import OnlineSourceClient
from .storage import load_documents
from .summarizer import build_summary
from .text import DOMAIN_TERMS, normalize_text, split_sentences, tokenize


FRONTIER_PATTERNS = [
    {
        "name": "DeerFlow / SuperAgent",
        "strength": "长任务拆解、子智能体、工具调用、记忆与沙箱执行",
        "integrated_as": "可追踪研究计划、Agent Trace、下一步行动队列",
    },
    {
        "name": "GraphRAG / LightRAG",
        "strength": "把资料组织成概念和关系，支持局部证据与全局脉络",
        "integrated_as": "轻量知识地图、来源覆盖、概念-证据关系",
    },
    {
        "name": "STORM / Co-STORM",
        "strength": "多视角信息寻求、带引用长答案、人机协同知识整理",
        "integrated_as": "研究简报、可追问问题、引用驱动的答案合成",
    },
    {
        "name": "RAGFlow / Onyx",
        "strength": "企业级 RAG、深度文档理解、连接器、可追溯结果",
        "integrated_as": "在线源 + 本地知识库混合、质量指标、稳定离线兜底",
    },
    {
        "name": "Self-RAG / Critic",
        "strength": "按需检索、自我批判、风险暴露和不确定性控制",
        "integrated_as": "CriticAgent 风险提示、可信度评分、证据短板提示",
    },
]


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
    decision_brief: dict[str, Any]
    trust_score: dict[str, Any]
    knowledge_map: dict[str, Any]
    next_questions: list[str]
    frontier_patterns: list[dict[str, str]]
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
            "decision_brief": self.decision_brief,
            "trust_score": self.trust_score,
            "knowledge_map": self.knowledge_map,
            "next_questions": self.next_questions,
            "frontier_patterns": self.frontier_patterns,
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
            "llm_error": llm_result.text if not llm_result.used_remote_model and self.llm.enabled else None
        }
        return type("AgentResult", (), {"payload": payload, "trace_message": "完成证据合成"})()


class CriticAgent:
    @traced("CriticAgent")
    def critique(self, result: dict[str, Any]) -> Any:
        citations = result.get("citations", [])
        risks: list[str] = []
        if not result.get("llm_used"):
            if result.get("llm_error"):
                risks.append(f"大模型调用失败，已回退到本地合成器。真实报错：{result['llm_error']}")
            else:
                risks.append("当前未检测到大模型 API Key，回答由本地确定性合成器生成；设置 KEYBOY_LLM_API_KEY 和 KEYBOY_LLM_MODEL 后会启用真实 LLM。")
        if len(citations) < 3:
            risks.append("证据数量不足，建议扩大在线源或增加子查询。")
        sources = {item.get("source") for item in citations}
        if len(sources) < 2 and citations:
            risks.append("来源多样性不足，建议引入更多数据库或网页源。")
        if not risks:
            risks.append("证据数量与来源多样性达到当前演示阈值。")
        return type("AgentResult", (), {"payload": risks, "trace_message": f"输出 {len(risks)} 条校验意见"})()


class StrategyAgent:
    @traced("StrategyAgent")
    def advise(
        self,
        query: str,
        plan: ResearchPlan,
        hits,
        synth: dict[str, Any],
        risks: list[str],
    ) -> Any:
        citations = synth.get("citations", [])
        trust_score = self._trust_score(citations, risks, bool(synth.get("llm_used")))
        knowledge_map = self._knowledge_map(hits)
        decision_brief = {
            "user_need": self._infer_user_need(query),
            "recommended_path": self._recommended_path(query, plan, citations, trust_score),
            "why_keyboy": self._why_keyboy(trust_score, citations),
            "tradeoffs": self._tradeoffs(query, citations),
        }
        next_questions = self._next_questions(query, knowledge_map)
        payload = {
            "decision_brief": decision_brief,
            "trust_score": trust_score,
            "knowledge_map": knowledge_map,
            "next_questions": next_questions,
            "frontier_patterns": FRONTIER_PATTERNS,
        }
        return type(
            "AgentResult",
            (),
            {"payload": payload, "trace_message": f"生成可信决策简报，可信度 {trust_score['score']}"},
        )()

    @staticmethod
    def _infer_user_need(query: str) -> str:
        lowered = query.lower()
        if any(term in query for term in ("课程", "课设", "验收", "项目", "设计", "答辩")):
            return "把前沿资料快速转成能讲清楚、能验收、能继续迭代的软件工程方案。"
        if any(term in query for term in ("对比", "选择", "选型", "哪个好", "最强", "最好")):
            return "在大量同类技术和项目里做出可信选型，而不是只看热度或宣传。"
        if any(term in query for term in ("论文", "综述", "研究", "调研", "报告")):
            return "用可引用证据完成研究综述，并暴露证据不足和不确定性。"
        if "github" in lowered or "开源" in query:
            return "从开源项目和公开资料中找出可落地能力，并沉淀成自己的产品特色。"
        return "用更短时间理解复杂技术问题，并获得可追踪、可复查的结论。"

    @staticmethod
    def _recommended_path(
        query: str,
        plan: ResearchPlan,
        citations: list[dict[str, Any]],
        trust_score: dict[str, Any],
    ) -> str:
        source_count = len({item.get("source") for item in citations if item.get("source")})
        if any(term in query for term in ("最强", "特色", "为什么", "用户", "需求")):
            return (
                "把 KeyBoy 定位成“前沿项目雷达 + 可信研究决策工作台”：用户输入目标后，系统自动规划检索、"
                "聚合在线证据、生成可引用结论、给出风险和下一步行动。核心卖点不是搜索框，而是把资料变成可执行决策。"
            )
        if "GraphRAG" in query or "LightRAG" in query:
            return (
                "以现有 Agentic Research 为主流程，优先补齐轻量知识地图和证据覆盖，再逐步扩展实体关系图谱、"
                "网页正文阅读和多轮研究任务。这样能保持课程项目稳定，同时吸收 GraphRAG/LightRAG 的强项。"
            )
        if source_count >= 2 and trust_score["score"] >= 70:
            return "当前证据覆盖较稳，可以直接进入方案设计、技术选型或报告撰写阶段。"
        return "先扩大资料源和子查询，再做最终选型；当前结论适合作为初稿，不适合直接当最终判断。"

    @staticmethod
    def _why_keyboy(trust_score: dict[str, Any], citations: list[dict[str, Any]]) -> list[str]:
        reasons = [
            "省时间：自动完成规划、检索、证据排序、合成和批判校验。",
            "可复查：每个结论都保留来源、分数、Agent Trace 和风险提示。",
            "能落地：把前沿项目能力翻译成适合课程设计和轻量部署的实现路线。",
            "不断网也能演示：在线研究失败时仍可用本地知识库稳定运行。",
        ]
        if trust_score["score"] >= 75:
            reasons.insert(1, "可信度可见：系统会量化证据数量、来源多样性、新鲜度和模型状态。")
        if len(citations) >= 6:
            reasons.append("信息密度高：一次研究能产出答案、证据、知识地图、追问和下一步行动。")
        return reasons

    @staticmethod
    def _tradeoffs(query: str, citations: list[dict[str, Any]]) -> list[str]:
        source_count = len({item.get("source") for item in citations if item.get("source")})
        tradeoffs = [
            "强功能与可维护性：优先做轻量知识地图、可信度和决策简报，避免一开始引入重型图数据库。",
            "在线能力与现场稳定：在线源提升前沿性，本地 fallback 保证课堂和演示可复现。",
        ]
        if any(term in query for term in ("GraphRAG", "LightRAG", "图谱", "关系")):
            tradeoffs.append("图谱增强很有价值，但第一阶段应先做可解释概念图，后续再升级实体抽取和社区摘要。")
        if source_count < 2:
            tradeoffs.append("当前来源覆盖偏窄，最终结论需要更多独立来源交叉验证。")
        return tradeoffs

    @staticmethod
    def _trust_score(citations: list[dict[str, Any]], risks: list[str], llm_used: bool) -> dict[str, Any]:
        source_count = len({item.get("source") for item in citations if item.get("source")})
        years: list[int] = []
        for item in citations:
            try:
                years.append(int(str(item.get("published_at", ""))[:4]))
            except ValueError:
                continue
        recent_ratio = sum(1 for year in years if year >= 2024) / max(1, len(years))
        evidence_score = min(35, len(citations) * 5)
        diversity_score = min(25, source_count * 8)
        recency_score = round(20 * recent_ratio)
        model_score = 10 if llm_used else 4
        risk_penalty = min(18, max(0, len([risk for risk in risks if "不足" in risk or "失败" in risk]) * 6))
        total = max(0, min(100, evidence_score + diversity_score + recency_score + model_score + 10 - risk_penalty))
        if total >= 82:
            level = "高"
        elif total >= 65:
            level = "中高"
        elif total >= 45:
            level = "中"
        else:
            level = "偏低"
        return {
            "score": int(total),
            "level": level,
            "signals": [
                {"name": "证据数量", "score": evidence_score, "max": 35, "detail": f"{len(citations)} 条引用证据"},
                {"name": "来源多样性", "score": diversity_score, "max": 25, "detail": f"{source_count} 个来源"},
                {"name": "资料新鲜度", "score": recency_score, "max": 20, "detail": f"{recent_ratio:.0%} 为 2024 年后资料"},
                {"name": "模型状态", "score": model_score, "max": 10, "detail": "远程 LLM" if llm_used else "本地 fallback"},
                {"name": "风险扣分", "score": -risk_penalty, "max": 0, "detail": f"{len(risks)} 条风险/校验意见"},
            ],
        }

    @staticmethod
    def _knowledge_map(hits) -> dict[str, Any]:
        concept_counter: Counter[str] = Counter()
        concept_sources: dict[str, set[str]] = {}
        source_counter: Counter[str] = Counter()
        edges: Counter[tuple[str, str]] = Counter()

        for hit in hits[:8]:
            doc = hit.document
            source_counter[doc.source] += 1
            terms = StrategyAgent._display_concepts(doc)
            for term in terms:
                concept_counter[term] += 1
                concept_sources.setdefault(term, set()).add(doc.source)
                edges[(term, doc.source)] += 1

        concepts = [
            {"name": name, "weight": weight, "sources": sorted(concept_sources.get(name, set()))}
            for name, weight in concept_counter.most_common(12)
        ]
        source_coverage = [{"name": name, "count": count} for name, count in source_counter.most_common()]
        edge_list = [
            {"from": concept, "to": source, "weight": weight, "label": "evidence-from"}
            for (concept, source), weight in edges.most_common(18)
        ]
        return {"concepts": concepts, "source_coverage": source_coverage, "edges": edge_list}

    @staticmethod
    def _display_concepts(doc: SearchDocument) -> list[str]:
        text = normalize_text(f"{doc.title} {' '.join(doc.tags)} {doc.category}").lower()
        concepts: list[str] = []

        for tag in doc.tags:
            tag = normalize_text(tag)
            if tag and tag.lower() not in {"online", doc.source.lower()}:
                concepts.append(tag)

        for term in DOMAIN_TERMS:
            if term.lower() in text:
                concepts.append(term)

        for token in tokenize(doc.title):
            is_ascii = token.isascii() and len(token) >= 3
            is_readable_cjk = not token.isascii() and len(token) >= 4
            if is_ascii or token in DOMAIN_TERMS or is_readable_cjk:
                concepts.append(token.upper() if token in {"rrf", "bm25", "api", "ndcg"} else token)

        seen: set[str] = set()
        unique: list[str] = []
        for concept in concepts:
            key = concept.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(concept)
            if len(unique) >= 8:
                break
        return unique

    @staticmethod
    def _next_questions(query: str, knowledge_map: dict[str, Any]) -> list[str]:
        concepts = [item["name"] for item in knowledge_map.get("concepts", [])[:4]]
        anchor = "、".join(concepts[:2]) if concepts else query
        questions = [
            f"{anchor} 在真实项目中的最小可行实现是什么？",
            f"{query} 需要哪些评测指标证明效果？",
            f"如果只用一周迭代，应该先做哪些能力？",
        ]
        if concepts:
            questions.append(f"{concepts[0]} 与 {concepts[-1]} 的关系是否能形成产品特色？")
        return questions[:4]


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
    strategy_agent: StrategyAgent = field(default_factory=StrategyAgent)

    def __post_init__(self) -> None:
        self.planner_agent = ResearchPlannerAgent(self.llm)
        self.ranker_agent = EvidenceRankerAgent(self.llm)
        self.synthesis_agent = SynthesisAgent(self.llm)

    def research(self, query: str, *, online: bool = True, include_local: bool = True, limit: int = 10) -> ResearchResult:
        traces: list[AgentTrace] = []
        started = time.perf_counter()

        plan_result, trace = self.planner_agent.plan(query)
        traces.append(trace)
        plan: ResearchPlan = plan_result.payload if plan_result else self.planner_agent._fallback_plan(query)

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

        strategy_result, trace = self.strategy_agent.advise(query, plan, hits, synth, risks)
        traces.append(trace)
        strategy = strategy_result.payload if strategy_result else {
            "decision_brief": {},
            "trust_score": {},
            "knowledge_map": {},
            "next_questions": [],
            "frontier_patterns": FRONTIER_PATTERNS,
        }

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
            decision_brief=strategy["decision_brief"],
            trust_score=strategy["trust_score"],
            knowledge_map=strategy["knowledge_map"],
            next_questions=strategy["next_questions"],
            frontier_patterns=strategy["frontier_patterns"],
            metrics=metrics,
            traces=traces,
        )

