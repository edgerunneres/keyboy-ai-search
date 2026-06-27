from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_TASKS_PATH = ROOT / "data" / "eval_tasks.json"

METRIC_DEFINITIONS = [
    {"id": "answer_completeness", "name": "答案完整度", "method": "按答案长度、结构化段落和关键发现数量做启发式评分"},
    {"id": "citation_support_rate", "name": "引用支持率", "method": "中/强支持且已读取正文的引用占比"},
    {"id": "source_count", "name": "来源数量", "method": "引用证据条数"},
    {"id": "source_diversity", "name": "来源多样性", "method": "引用来源去重数量"},
    {"id": "body_read", "name": "是否读取正文", "method": "source_read_success 是否大于 0"},
    {"id": "failure", "name": "失败率", "method": "任务是否失败或存在失败智能体"},
    {"id": "latency_ms", "name": "总耗时", "method": "后端 metrics.latency_ms"},
    {"id": "model_cost", "name": "模型成本", "method": "本地兜底模式记为 0，远程模型以平台账单为准"},
]


def load_eval_tasks(path: Path = EVAL_TASKS_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def score_result(result: dict[str, Any]) -> dict[str, Any]:
    answer = str(result.get("answer") or "")
    citations = result.get("citations") or []
    findings = result.get("findings") or []
    metrics = result.get("metrics") or {}
    traces = result.get("traces") or []
    has_sections = answer.count("##") >= 2
    answer_completeness = min(100, len(answer) // 12 + len(findings) * 8 + (18 if has_sections else 0))
    failed_agents = [trace for trace in traces if trace.get("status") == "error"]
    return {
        "answer_completeness": int(answer_completeness),
        "citation_support_rate": metrics.get("citation_support_rate", 0),
        "source_count": len(citations),
        "source_diversity": metrics.get("source_diversity", 0),
        "body_read": bool(metrics.get("source_read_success", 0)),
        "failure": bool(failed_agents or metrics.get("task_status") == "failed"),
        "latency_ms": metrics.get("latency_ms", 0),
        "model_cost": 0 if not metrics.get("llm_used") else metrics.get("model_cost", "provider-billed"),
    }


def summarize_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"cases": 0}
    scores = [row["scores"] for row in rows]
    return {
        "cases": len(rows),
        "avg_answer_completeness": round(sum(item["answer_completeness"] for item in scores) / len(scores), 2),
        "avg_citation_support_rate": round(sum(float(item["citation_support_rate"] or 0) for item in scores) / len(scores), 3),
        "avg_source_count": round(sum(item["source_count"] for item in scores) / len(scores), 2),
        "avg_source_diversity": round(sum(item["source_diversity"] for item in scores) / len(scores), 2),
        "body_read_rate": round(sum(1 for item in scores if item["body_read"]) / len(scores), 3),
        "failure_rate": round(sum(1 for item in scores if item["failure"]) / len(scores), 3),
        "avg_latency_ms": round(sum(float(item["latency_ms"] or 0) for item in scores) / len(scores), 2),
    }
