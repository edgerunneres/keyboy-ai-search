from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .agents import CleanAgent, IndexAgent, traced
from .index import HybridSearchIndex
from .llm import LLMProvider
from .models import AgentTrace, SearchDocument
from .online_sources import OnlineSourceClient
from .source_reader import SourceReadSummary, SourceReader, source_identity
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


class ResearchCancelled(Exception):
    def __init__(self, message: str, *, traces: list[AgentTrace] | None = None, metrics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.traces = traces or []
        self.metrics = metrics or {}


class ResearchPlannerAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @traced("ResearchPlannerAgent")
    def plan(self, query: str, on_chunk: Any = None) -> Any:
        fallback = self._fallback_plan(query)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research planning agent for an online LLM multi-agent search system. "
                    "Return strict JSON with intent, subqueries, source_plan, required_evidence. "
                    "Always output the values in Chinese."
                ),
            },
            {"role": "user", "content": query},
        ]
        parsed, llm_result = self.llm.chat_json(messages, fallback=fallback.__dict__, on_chunk=on_chunk)
        plan = ResearchPlan(
            intent=str(parsed.get("intent") or fallback.intent),
            subqueries=self._normalize_subqueries(parsed.get("subqueries", fallback.subqueries), fallback.subqueries, query),
            source_plan=self._normalize_source_plan(parsed.get("source_plan", fallback.source_plan), fallback.source_plan),
            required_evidence=[str(x) for x in parsed.get("required_evidence", fallback.required_evidence)][:6],
            llm_used=llm_result.used_remote_model,
        )
        return type("AgentResult", (), {"payload": plan, "trace_message": f"规划 {len(plan.subqueries)} 个检索方向"})()

    @staticmethod
    def _normalize_subqueries(raw_subqueries: Any, fallback: list[str], query: str = "") -> list[str]:
        if not isinstance(raw_subqueries, list):
            raw_subqueries = [raw_subqueries]
        cleaned: list[str] = []
        seen: set[str] = set()
        clean_query = normalize_text(query)
        query_key = ResearchPlannerAgent._subquery_key(clean_query)
        for item in raw_subqueries:
            text = ResearchPlannerAgent._clean_subquery_text(str(item or ""), clean_query)
            if len(text) < 4:
                continue
            key = ResearchPlannerAgent._subquery_key(text)
            if key == query_key:
                continue
            if key in seen:
                continue
            cleaned.append(text)
            seen.add(key)
        if cleaned:
            return cleaned[:6]
        if fallback:
            return ResearchPlannerAgent._normalize_subqueries(fallback, [], query)[:6]
        return []

    @staticmethod
    def _clean_subquery_text(value: str, query: str = "") -> str:
        text = normalize_text(value).strip(" -_\"'“”")
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
        if query and text.startswith(query):
            suffix = text[len(query):].lstrip("：: -_，,。；;")
            text = f"{ResearchPlannerAgent._query_topic(query)}{suffix}".strip() if suffix else ""
        return text

    @staticmethod
    def _subquery_key(value: str) -> str:
        text = normalize_text(value).lower()
        return re.sub(r"[\s：:，,。；;！？?\"'“”\-_/]+", "", text)

    @staticmethod
    def _normalize_source_plan(raw_sources: Any, fallback: list[str]) -> list[str]:
        if not isinstance(raw_sources, list):
            raw_sources = [raw_sources]
        mapped: list[str] = []
        for item in raw_sources:
            source = str(item or "").lower()
            expanded: list[str] = []
            if "openalex" in source:
                expanded.append("openalex")
            if "semantic" in source or "scholar" in source:
                expanded.append("semanticscholar")
            if "arxiv" in source or "preprint" in source:
                expanded.append("arxiv")
            if "crossref" in source or "doi" in source:
                expanded.append("crossref")
            if any(term in source for term in ("paper", "peer", "academic", "publication", "journal", "conference", "acl", "neurips", "research")):
                expanded.extend(fallback)
            for canonical in expanded:
                if canonical not in mapped:
                    mapped.append(canonical)
        return (mapped or fallback)[:4]

    @staticmethod
    def _fallback_plan(query: str) -> ResearchPlan:
        topic = ResearchPlannerAgent._query_topic(query)
        subqueries = [
            f"{topic}最新论文与技术综述",
            f"{topic}架构差异与适用场景",
            f"{topic}开源项目与系统实现",
            "课程项目落地方案与评测指标",
        ]
        return ResearchPlan(
            intent="在线研究与证据合成",
            subqueries=subqueries,
            source_plan=["openalex", "semanticscholar", "arxiv", "crossref"],
            required_evidence=["最新论文", "高引用研究", "开源项目/框架", "可落地架构"],
            llm_used=False,
        )

    @staticmethod
    def _query_topic(query: str) -> str:
        clean_query = normalize_text(query) or query
        english_terms = re.findall(r"[A-Za-z][A-Za-z0-9+.#/-]*(?:\s+[A-Za-z][A-Za-z0-9+.#/-]*)*", clean_query)
        latin_topic = " ".join(term.strip() for term in english_terms if term.strip())
        latin_topic = re.sub(r"\s+", " ", latin_topic).strip()
        if latin_topic:
            return f"{latin_topic} "
        topic = re.sub(r"(请|帮我|帮忙|分析|研究|一下|怎么|如何|怎样|为什么|是否|能否|可以|吗|呢|？|\\?)", " ", clean_query)
        topic = re.sub(r"\s+", " ", topic).strip(" ：:，,。；;")
        return f"{topic or clean_query} "


class OnlineDiscoveryAgent:
    def __init__(self, client: OnlineSourceClient | None = None) -> None:
        self.client = client or OnlineSourceClient()

    @traced("OnlineDiscoveryAgent")
    def discover(self, plan: ResearchPlan, *, online: bool = True, on_progress: Any = None) -> Any:
        if not online:
            return type(
                "AgentResult",
                (),
                {"payload": ([], ["已关闭在线研究源，当前仅使用本地知识库。"]), "trace_message": "跳过在线源"},
            )()
        docs: list[SearchDocument] = []
        warnings: list[str] = []
        try:
            max_queries = max(1, int(os.getenv("KEYBOY_ONLINE_QUERY_LIMIT", "1")))
        except ValueError:
            max_queries = 1
        for subquery in plan.subqueries[:max_queries]:
            if on_progress:
                on_progress(f"发现在线资料: 准备查询 '{subquery}'")
            found, source_warnings = self.client.search(subquery, plan.source_plan, on_progress=on_progress)
            docs.extend(found)
            warnings.extend(source_warnings)
        unique: dict[str, SearchDocument] = {}
        for doc in docs:
            unique.setdefault(source_identity(doc), doc)
        return type(
            "AgentResult",
            (),
            {
                "payload": (list(unique.values()), self._summarize_warnings(warnings)),
                "trace_message": f"在线发现 {len(unique)} 篇资料",
            },
        )()

    @staticmethod
    def _summarize_warnings(warnings: list[str]) -> list[str]:
        if not warnings:
            return []
        limited = sorted({OnlineDiscoveryAgent._warning_source(item) for item in warnings if "限流" in item})
        timed_out = sorted({OnlineDiscoveryAgent._warning_source(item) for item in warnings if "超时" in item})
        denied = sorted({item for item in warnings if "拒绝访问" in item})
        other = sorted(
            {
                OnlineDiscoveryAgent._warning_source(item)
                for item in warnings
                if item and all(marker not in item for marker in ("限流", "超时", "拒绝访问"))
            }
        )
        messages: list[str] = []
        if limited:
            messages.append(f"{'、'.join(limited)} 返回 429 限流；已跳过这些源并继续研究。")
        if timed_out:
            messages.append(f"{'、'.join(timed_out)} 响应超时；已使用其他可用证据继续。")
        messages.extend(denied)
        if other:
            messages.append(f"{'、'.join(other)} 暂不可用；已使用可用证据和本地知识库继续。")
        return messages or ["部分在线源暂不可用，已使用可用证据继续。"]

    @staticmethod
    def _warning_source(warning: str) -> str:
        for marker in (" 限流", " 超时", " 拒绝访问", " HTTP", " 暂不可用"):
            if marker in warning:
                return warning.split(marker, 1)[0]
        return warning


class SourceReadAgent:
    def __init__(self, reader: SourceReader | None = None) -> None:
        self.reader = reader or SourceReader()

    @traced("SourceReadAgent")
    def read(self, documents: list[SearchDocument], *, online: bool = True, on_progress: Any = None, should_cancel: Any = None) -> Any:
        if not online or not documents:
            return type(
                "AgentResult",
                (),
                {"payload": SourceReadSummary(), "trace_message": "跳过来源正文读取"},
            )()
        summary = self.reader.read_documents(documents, on_progress=on_progress, should_cancel=should_cancel)
        return type(
            "AgentResult",
            (),
            {"payload": summary, "trace_message": f"读取 {summary.readable}/{summary.attempted} 个来源正文"},
        )()


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
    def synthesize(self, query: str, hits, on_chunk: Any = None) -> Any:
        citations = []
        context_blocks = []
        for idx, hit in enumerate(hits[:8], start=1):
            sentences = split_sentences(hit.document.content)
            evidence = sentences[0] if sentences else hit.document.content[:240]
            original_excerpt = hit.snippet or evidence
            risk_flags = self._citation_risks(hit.document)
            citations.append(
                {
                    "id": idx,
                    "title": hit.document.title,
                    "source": hit.document.source,
                    "url": hit.document.url,
                    "published_at": hit.document.published_at,
                    "score": round(hit.score, 2),
                    "evidence": evidence,
                    "supporting_claim": self._supporting_claim(query, evidence),
                    "original_excerpt": original_excerpt,
                    "support_level": self._support_level(hit.score),
                    "risk_flags": risk_flags,
                    "read_status": self._read_status(hit.document),
                }
            )
            context_blocks.append(f"[{idx}] {hit.document.title}\n{evidence}\nURL: {hit.document.url}")

        fallback_summary, fallback_findings = build_summary(query, hits)
        evidence_lines = "\n".join(f"- [{c['id']}] {c['title']}" for c in citations[:5])
        fallback_answer = (
            f"## 核心结论\n{fallback_summary}\n\n"
            f"## 证据来源\n{evidence_lines}"
        )
        if not citations:
            fallback_answer = "## 证据不足\n未获得足够证据。建议开启在线源、填写在线源 API 信息，或提供更具体的问题。"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a citation-grounded synthesis agent. Answer in Chinese. "
                    "Use only the provided evidence and cite sources like [1], [2]. "
                    "Write as a polished research brief in Markdown with clear sections: "
                    "## 核心结论, ## 关键发现, ## 不确定性, ## 证据引用. "
                    "Use short paragraphs and bullets. Do not output JSON, code fences, raw planning notes, or decorative symbols."
                ),
            },
            {"role": "user", "content": f"问题：{query}\n\n证据：\n" + "\n\n".join(context_blocks)},
        ]
        if not self.llm.enabled and on_chunk:
            import time
            on_chunk("启动本地确定性信息抽取模块...\n")
            time.sleep(0.4)
            for finding in fallback_findings[:3]:
                on_chunk(f"提取核心观点：{finding[:20]}...\n")
                time.sleep(0.4)
            on_chunk("正在整合结构化段落...\n")
            time.sleep(0.4)
            on_chunk("本地合成完毕。\n")

        llm_result = self.llm.chat(messages, temperature=0.3, max_tokens=1800, on_chunk=on_chunk)
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

    @staticmethod
    def _supporting_claim(query: str, evidence: str) -> str:
        sentence = split_sentences(evidence)
        if sentence:
            return f"支撑对“{query[:32]}”的关键判断：{sentence[0][:120]}"
        return f"支撑对“{query[:32]}”的资料判断。"

    @staticmethod
    def _support_level(score: float) -> str:
        if score >= 70:
            return "强"
        if score >= 40:
            return "中"
        return "弱"

    @staticmethod
    def _read_status(document: SearchDocument) -> str:
        joined = " ".join(document.tags)
        if "body-read" in joined or "source-read" in joined:
            return "已读正文"
        return "仅摘要"

    @staticmethod
    def _citation_risks(document: SearchDocument) -> list[str]:
        risks: list[str] = []
        prefix = f"《{document.title}》" if document.title else f"链接 {document.url}"
        joined = " ".join(document.tags)
        if "body-read" not in joined and "source-read" not in joined:
            risks.append(f"{prefix} 未能提取正文，仅依靠摘要可能导致信息不全")
        if "read:pdf" in joined:
            risks.append(f"{prefix} 为 PDF 文件，复杂排版或图表内容可能提取丢失")
        if not document.url.startswith(("http://", "https://", "doi:")):
            risks.append(f"{prefix} 未提供可直接打开的网页或 DOI 链接，系统只能按标题、摘要和来源信息交叉验证")
        try:
            year = int(str(document.published_at)[:4])
            if year and year < 2021:
                risks.append(f"{prefix} 发表较早（{year}年），注意时效性")
        except ValueError:
            pass
        return risks


class CriticAgent:
    @traced("CriticAgent")
    def critique(self, result: dict[str, Any]) -> Any:
        citations = result.get("citations", [])
        risks: list[str] = []
        if not result.get("llm_used"):
            if result.get("llm_error"):
                risks.append(f"大模型调用失败，已回退到本地合成器。{result['llm_error']}")
            else:
                risks.append("当前未配置远程大模型密钥，回答由本地确定性合成器生成；在模型面板配置后会启用真实远程大模型。")
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
        knowledge_map = self._knowledge_map(query, hits)
        decision_brief = {
            "user_need": self._infer_user_need(query),
            "verdict": self._verdict(trust_score, citations, risks),
            "evidence_basis": self._evidence_basis(citations, risks, bool(synth.get("llm_used"))),
            "recommended_path": self._recommended_path(query, plan, citations, trust_score),
            "why_keyboy": self._why_keyboy(trust_score, citations),
            "tradeoffs": self._tradeoffs(query, citations, risks, bool(synth.get("llm_used"))),
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
        if source_count >= 2 and trust_score["score"] >= 70:
            return "可以把本次研究作为方案设计、技术选型或报告撰写的依据，但最终答辩前仍建议复查关键引用。"
        if len(citations) >= 3:
            return "适合作为研究初稿和课堂讲解材料；如果要形成最终判断，需要补充更多独立来源。"
        return "当前更适合做探索性线索，不适合直接作为最终结论；建议扩大资料源或细化子查询后再决策。"

    @staticmethod
    def _verdict(trust_score: dict[str, Any], citations: list[dict[str, Any]], risks: list[str]) -> str:
        score = trust_score.get("score", 0)
        level = trust_score.get("level", "未知")
        if score >= 75:
            scope = "可用于支撑主要判断"
        elif score >= 55:
            scope = "可用于支撑初稿和课堂展示"
        else:
            scope = "只适合作为线索，不宜直接下最终结论"
        if not citations:
            return "暂未形成可复查证据，当前结果不能作为可信决策依据。"
        if any("失败" in risk or "不足" in risk for risk in risks):
            return f"可信度{level}（{score}分），{scope}；但仍存在来源或证据短板。"
        return f"可信度{level}（{score}分），{scope}。"

    @staticmethod
    def _evidence_basis(citations: list[dict[str, Any]], risks: list[str], llm_used: bool) -> str:
        source_count = len({item.get("source") for item in citations if item.get("source")})
        strong_count = sum(1 for item in citations if item.get("support_level") == "强")
        readable_count = sum(1 for item in citations if item.get("read_status") == "已读正文")
        model_state = "远程大模型" if llm_used else "本地兜底模式"
        return (
            f"基于 {len(citations)} 条引用、{source_count} 类来源、{strong_count} 条强支持证据；"
            f"{readable_count} 条证据已读取正文，模型状态为{model_state}，当前记录 {len(risks)} 条风险/校验意见。"
        )

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
    def _tradeoffs(query: str, citations: list[dict[str, Any]], risks: list[str], llm_used: bool) -> list[str]:
        source_count = len({item.get("source") for item in citations if item.get("source")})
        tradeoffs = [
            "速度与严谨度：当前结果适合快速形成判断；更严谨的最终结论需要继续补证和复核来源。",
            "前沿性与可复现：在线来源提升新鲜度；课堂展示仍要保留本地兜底模式保证稳定。",
        ]
        if not llm_used:
            tradeoffs.append("模型能力与稳定性：本地兜底模式可复现，但语言质量和综合判断弱于真实远程大模型。")
        if source_count < 2:
            tradeoffs.append("覆盖面与结论强度：来源类型偏少时，结论应降级为候选判断。")
        if any("正文" in risk or "直接打开" in risk for risk in risks):
            tradeoffs.append("可验证性与覆盖率：部分来源只能按摘要或元数据验证，引用时应说明证据强度。")
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
                {"name": "模型状态", "score": model_score, "max": 10, "detail": "远程大模型" if llm_used else "本地兜底模式"},
                {"name": "风险扣分", "score": -risk_penalty, "max": 0, "detail": f"{len(risks)} 条风险/校验意见"},
            ],
        }

    @staticmethod
    def _knowledge_map(query: str, hits) -> dict[str, Any]:
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


class EvaluatorAgent:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    @traced("EvaluatorAgent")
    def evaluate(self, query: str, hits) -> Any:
        if not self.llm.enabled:
            sources = {hit.document.source for hit in hits}
            if len(sources) >= 2 and len(hits) >= 3:
                payload = {"sufficient": True, "new_subqueries": []}
            else:
                payload = {"sufficient": False, "new_subqueries": [f"{ResearchPlannerAgent._query_topic(query)}补充综述与对比证据"]}
            return type("AgentResult", (), {"payload": payload, "trace_message": "启发式评估"})()

        context_snippets = "\n".join(
            f"来源: {hit.document.source}\n摘要: {hit.document.content[:150]}"
            for hit in hits[:5]
        )
        prompt = f"""评估以下检索到的证据是否足以回答用户的研究主题。
主题: {query}
证据片段:
{context_snippets}

如果证据充足，请返回: {{"sufficient": true, "new_subqueries": []}}
如果证据不足，请返回: {{"sufficient": false, "new_subqueries": ["补充查询1", "补充查询2"]}}
仅返回 JSON，不包含其他内容。
"""
        response = self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=500)
        try:
            cleaned = response.text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            payload = json.loads(cleaned.strip())
        except Exception:
            payload = {"sufficient": True, "new_subqueries": []}

        return type("AgentResult", (), {"payload": payload, "trace_message": "大模型证据评估"})()


@dataclass
class AgenticKeyBoySystem:
    llm: LLMProvider = field(default_factory=LLMProvider)
    clean_agent: CleanAgent = field(default_factory=CleanAgent)
    index_agent: IndexAgent = field(default_factory=IndexAgent)
    planner_agent: ResearchPlannerAgent = field(init=False)
    discovery_agent: OnlineDiscoveryAgent = field(default_factory=OnlineDiscoveryAgent)
    source_read_agent: SourceReadAgent = field(default_factory=SourceReadAgent)
    evaluator_agent: EvaluatorAgent = field(init=False)
    ranker_agent: EvidenceRankerAgent = field(init=False)
    synthesis_agent: SynthesisAgent = field(init=False)
    critic_agent: CriticAgent = field(default_factory=CriticAgent)
    strategy_agent: StrategyAgent = field(default_factory=StrategyAgent)

    def __post_init__(self) -> None:
        self.planner_agent = ResearchPlannerAgent(self.llm)
        self.ranker_agent = EvidenceRankerAgent(self.llm)
        self.synthesis_agent = SynthesisAgent(self.llm)
        self.evaluator_agent = EvaluatorAgent(self.llm)

    def research(
        self,
        query: str,
        *,
        online: bool = True,
        include_local: bool = True,
        limit: int = 10,
        on_event: Any = None,
        should_cancel: Any = None,
        on_trace: Any = None,
    ) -> ResearchResult:
        traces: list[AgentTrace] = []
        started = time.perf_counter()
        all_warnings: list[str] = []
        online_document_count = 0
        source_read_reports: list[dict[str, Any]] = []
        cleaned: list[SearchDocument] = []
        hits = []
        ranked: dict[str, Any] = {"hits": [], "profile": {}}
        index = HybridSearchIndex()

        self.llm_stream_buffer = ""
        def handle_chunk(chunk: str):
            self.llm_stream_buffer += chunk
            if on_event:
                on_event({"type": "chunk", "chunk": chunk})

        def set_status(msg: str):
            self.current_status = msg
            handle_chunk(f"{msg}\n")
            if on_event:
                on_event({"type": "status", "message": msg})

        def append_trace(trace: AgentTrace) -> None:
            traces.append(trace)
            if trace.status == "error":
                all_warnings.append(f"{trace.name} 失败：{trace.message}")
            if on_trace:
                on_trace([item.to_dict() for item in traces])

        def check_cancel() -> None:
            if should_cancel and should_cancel():
                metrics = {
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "online_documents": online_document_count,
                    "indexed_documents": len(cleaned),
                    "result_count": len(hits),
                    "cancelled": True,
                }
                raise ResearchCancelled("研究已取消，已保留已完成阶段日志。", traces=traces, metrics=metrics)

        check_cancel()
        set_status("正在规划研究方案...")
        plan_result, trace = self.planner_agent.plan(query, on_chunk=handle_chunk)
        append_trace(trace)
        check_cancel()
        plan: ResearchPlan = plan_result.payload if plan_result else self.planner_agent._fallback_plan(query)

        all_documents = []
        if include_local:
            all_documents.extend(load_documents())

        max_iterations = 2
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            check_cancel()
            set_status(f"[第 {iteration} 轮迭代] 正在发现在线资料...")
            discovery_result, trace = self.discovery_agent.discover(plan, online=online, on_progress=set_status)
            append_trace(trace)
            check_cancel()
            online_docs, source_warnings = discovery_result.payload if discovery_result else ([], [trace.message])

            all_documents.extend(online_docs)
            online_document_count += len(online_docs)
            all_warnings.extend(source_warnings)

            if online_docs:
                set_status(f"[第 {iteration} 轮迭代] 正在打开来源并读取正文...")
            source_read_result, trace = self.source_read_agent.read(
                online_docs,
                online=online,
                on_progress=set_status,
                should_cancel=should_cancel,
            )
            append_trace(trace)
            check_cancel()
            source_read_summary = source_read_result.payload if source_read_result else SourceReadSummary()
            source_read_reports.extend(source_read_summary.reports)
            all_documents.extend(source_read_summary.documents)
            all_warnings.extend(source_read_summary.warnings[:8])

            set_status(f"[第 {iteration} 轮迭代] 正在清洗与整理文档...")
            clean_result, trace = self.clean_agent.clean(all_documents)
            append_trace(trace)
            check_cancel()
            cleaned = clean_result.payload if clean_result else []

            set_status(f"[第 {iteration} 轮迭代] 正在构建知识索引...")
            index_result, trace = self.index_agent.build(cleaned)
            append_trace(trace)
            check_cancel()
            index = index_result.payload if index_result else HybridSearchIndex()

            set_status(f"[第 {iteration} 轮迭代] 正在检索相关证据...")
            rank_result, trace = self.ranker_agent.rank(index, query, limit=limit)
            append_trace(trace)
            check_cancel()
            ranked = rank_result.payload if rank_result else {"hits": [], "profile": {}}
            hits = ranked["hits"]

            if iteration < max_iterations:
                set_status(f"[第 {iteration} 轮迭代] 评估证据是否充足...")
                eval_result, trace = self.evaluator_agent.evaluate(query, hits)
                append_trace(trace)
                check_cancel()
                eval_payload = eval_result.payload if eval_result else {"sufficient": True, "new_subqueries": []}

                if eval_payload.get("sufficient"):
                    set_status("证据充足，准备合成最终答案。")
                    break
                else:
                    new_subs = ResearchPlannerAgent._normalize_subqueries(eval_payload.get("new_subqueries", []), [], query)
                    if not new_subs:
                        break
                    set_status(f"发现知识盲区，生成补充查询: {', '.join(new_subs)}")
                    plan.subqueries = new_subs

        check_cancel()
        set_status("正在合成研究答案（调用大模型时可能较慢）...")
        synth_result, trace = self.synthesis_agent.synthesize(query, hits, on_chunk=handle_chunk)
        append_trace(trace)
        check_cancel()
        synth = synth_result.payload if synth_result else {"answer": "", "citations": [], "findings": [], "llm_used": False, "model": ""}

        set_status("正在进行批判与风险校验（调用大模型时可能较慢）...")
        critique_result, trace = self.critic_agent.critique(synth)
        append_trace(trace)
        check_cancel()
        risks = list(dict.fromkeys(all_warnings[:10] + (critique_result.payload if critique_result else [])))

        set_status("正在生成最终研究简报（调用大模型时可能较慢）...")
        strategy_result, trace = self.strategy_agent.advise(query, plan, hits, synth, risks)
        append_trace(trace)
        if trace.status == "error":
            risks = list(dict.fromkeys(risks + [f"{trace.name} 失败：{trace.message}"]))
        check_cancel()
        strategy = strategy_result.payload if strategy_result else self._fallback_strategy(query, plan, hits, synth, risks)

        failed_agents = [
            {"name": trace.name, "message": trace.message}
            for trace in traces
            if trace.status == "error"
        ]
        body_read_count = sum(1 for item in source_read_reports if item.get("status") in {"ok", "partial"})
        source_diversity = len({citation.get("source") for citation in synth.get("citations", []) if citation.get("source")})
        supportable_citations = [
            citation for citation in synth.get("citations", [])
            if citation.get("support_level") in {"强", "中"} and citation.get("read_status") == "已读正文"
        ]

        latency_ms = (time.perf_counter() - started) * 1000
        metrics = {
            "latency_ms": round(latency_ms, 2),
            "online_documents": online_document_count,
            "indexed_documents": len(cleaned),
            "result_count": len(hits),
            "llm_used": bool(synth.get("llm_used")),
            "llm_model": synth.get("model") or "deterministic-fallback",
            "query_profile": ranked.get("profile", {}),
            "index": index.stats(),
            "source_read_attempted": len(source_read_reports),
            "source_read_success": body_read_count,
            "source_read_reports": [
                {key: item.get(key) for key in ("url", "title", "source", "source_type", "status", "length", "risks")}
                for item in source_read_reports
            ],
            "source_diversity": source_diversity,
            "citation_support_rate": round(len(supportable_citations) / max(1, len(synth.get("citations", []))), 3),
            "failed_agents": failed_agents,
            "model_cost": "未配置远程模型" if not synth.get("llm_used") else "由模型平台计费统计为准",
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

    @staticmethod
    def _fallback_strategy(query: str, plan: ResearchPlan, hits, synth: dict[str, Any], risks: list[str]) -> dict[str, Any]:
        citations = synth.get("citations", [])
        trust_score = StrategyAgent._trust_score(citations, risks, bool(synth.get("llm_used")))
        knowledge_map = StrategyAgent._knowledge_map(query, hits)
        return {
            "decision_brief": {
                "user_need": StrategyAgent._infer_user_need(query),
                "verdict": StrategyAgent._verdict(trust_score, citations, risks),
                "evidence_basis": StrategyAgent._evidence_basis(citations, risks, bool(synth.get("llm_used"))),
                "recommended_path": StrategyAgent._recommended_path(query, plan, citations, trust_score),
                "why_keyboy": StrategyAgent._why_keyboy(trust_score, citations),
                "tradeoffs": StrategyAgent._tradeoffs(query, citations, risks, bool(synth.get("llm_used"))),
            },
            "trust_score": trust_score,
            "knowledge_map": knowledge_map,
            "next_questions": StrategyAgent._next_questions(query, knowledge_map),
            "frontier_patterns": FRONTIER_PATTERNS,
        }
