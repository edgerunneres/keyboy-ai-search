from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import threading
from typing import Any, Optional

import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from fastapi import FastAPI, HTTPException

from .agentic import AgenticKeyBoySystem, ResearchCancelled
from .agents import KeyBoySystem
from .eval_suite import METRIC_DEFINITIONS, load_eval_tasks
from .task_store import TaskStore


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
SYSTEM = KeyBoySystem()
AGENTIC_SYSTEM = AgenticKeyBoySystem()
TASK_STORE = TaskStore()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LLMConfig(BaseModel):
    provider: str = "bailian"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout: Any = None
    enable_thinking: Optional[bool] = None


class SourcesConfig(BaseModel):
    semantic_scholar_api_key: str = ""
    openalex_api_key: str = ""
    openalex_mailto: str = ""
    crossref_mailto: str = ""
    timeout: Any = None
    per_source_limit: Any = None


class ProjectPayload(BaseModel):
    name: str = ""


class ConversationPayload(BaseModel):
    title: str = ""


class TaskPayload(BaseModel):
    query: str = ""
    project_id: str = "default"
    conversation_id: Optional[str] = None
    online: bool = True
    include_local: bool = True
    limit: int = 8
    origin_task_id: Optional[str] = None


class MovePayload(BaseModel):
    project_id: str


class ArchivePayload(BaseModel):
    archived: bool = True


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def task_source_config(payload: TaskPayload) -> dict[str, Any]:
    return {
        "online": bool(payload.online),
        "include_local": bool(payload.include_local),
        "limit": max(1, min(20, int(payload.limit or 8))),
    }


def task_payload_from_config(task: dict[str, Any]) -> TaskPayload:
    source_config = task.get("source_config") or {}
    return TaskPayload(
        query=task.get("query", ""),
        project_id=task.get("project_id", "default"),
        conversation_id=task.get("conversation_id"),
        online=bool(source_config.get("online", True)),
        include_local=bool(source_config.get("include_local", True)),
        limit=int(source_config.get("limit", 8) or 8),
        origin_task_id=task.get("origin_task_id"),
    )


def task_result_envelope(task: dict[str, Any]) -> dict[str, Any]:
    return {"task": task, "result": task.get("result") or {}}


def partial_result(query: str, message: str, *, traces: list[dict[str, Any]], metrics: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "query": query,
        "answer": message,
        "plan": {"intent": "", "subqueries": [], "source_plan": [], "required_evidence": [], "llm_used": False},
        "citations": [],
        "findings": [],
        "risks": [message],
        "decision_brief": {},
        "trust_score": {},
        "knowledge_map": {},
        "next_questions": [],
        "frontier_patterns": [],
        "metrics": {**metrics, "task_status": status},
        "traces": traces,
    }


def run_task(task_id: str, emit: Any = None) -> dict[str, Any]:
    task = TASK_STORE.get_task(task_id, include_result=True)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] == "cancelled":
        return task

    payload = task_payload_from_config(task)
    latest = TASK_STORE.get_task(task_id, include_result=False)
    if latest and latest["status"] == "cancelled":
        return latest
    running_task = TASK_STORE.update_status(task_id, "running")
    if not running_task or running_task.get("status") != "running":
        return running_task or TASK_STORE.get_task(task_id, include_result=True)
    if emit:
        emit({"type": "task", "task": running_task})

    def is_cancelled() -> bool:
        current = TASK_STORE.get_task(task_id, include_result=False)
        return bool(current and current["status"] == "cancelled")

    def save_trace(traces: list[dict[str, Any]]) -> None:
        TASK_STORE.save_partial(task_id, traces=traces)

    try:
        result = AGENTIC_SYSTEM.research(
            payload.query,
            online=payload.online,
            include_local=payload.include_local,
            limit=payload.limit,
            on_event=emit,
            should_cancel=is_cancelled,
            on_trace=save_trace,
        )
        latest = TASK_STORE.get_task(task_id, include_result=False)
        if latest and latest["status"] == "cancelled":
            raise ResearchCancelled("研究已取消，已保留已完成阶段日志。", traces=result.traces, metrics=result.metrics)
        saved = TASK_STORE.save_result(task_id, result.to_dict(), status="completed")
        return saved or TASK_STORE.get_task(task_id, include_result=True)
    except ResearchCancelled as exc:
        traces = [trace.to_dict() for trace in exc.traces]
        result = partial_result(payload.query, str(exc), traces=traces, metrics=exc.metrics, status="cancelled")
        TASK_STORE.update_status(task_id, "cancelled", error_message=str(exc))
        saved = TASK_STORE.save_result(task_id, result, status="cancelled")
        if emit:
            emit({"type": "cancelled", "task": TASK_STORE.get_task(task_id, include_result=True), "message": str(exc)})
        return saved or TASK_STORE.get_task(task_id, include_result=True)
    except Exception as exc:
        current = TASK_STORE.get_task(task_id, include_result=True) or task
        if current.get("status") == "cancelled":
            if emit:
                emit({"type": "cancelled", "task": current, "message": current.get("error_message") or "研究已取消。"})
            return current
        traces = (current.get("result") or {}).get("traces") or []
        if not traces:
            traces = (current.get("result") or {}).get("traces") or []
        message = f"研究失败：{exc}"
        result = partial_result(payload.query, message, traces=traces, metrics={}, status="failed")
        TASK_STORE.save_result(task_id, result, status="failed")
        TASK_STORE.update_status(task_id, "failed", error_message=message)
        if emit:
            emit({"type": "error", "message": message, "task": TASK_STORE.get_task(task_id, include_result=True)})
        return TASK_STORE.get_task(task_id, include_result=True)


def stream_task(task_id: str) -> EventSourceResponse:
    q_queue: queue.Queue = queue.Queue()
    q_queue.put({"type": "task", "task": TASK_STORE.get_task(task_id, include_result=True)})

    def emit(event: dict[str, Any]) -> None:
        q_queue.put(event)

    def worker() -> None:
        try:
            task = run_task(task_id, emit=emit)
            latest = TASK_STORE.get_task(task_id, include_result=True) if task else None
            if latest and latest.get("status") == "completed":
                q_queue.put({"type": "complete", "task": latest, "result": latest.get("result") or {}})
        finally:
            q_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_generator():
        while True:
            event = q_queue.get()
            if event is None:
                break
            yield {"data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@app.on_event("startup")
def startup_event():
    SYSTEM.bootstrap()
    TASK_STORE.ensure_schema()


@app.options("/{full_path:path}")
def options_preflight(full_path: str):
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


@app.get("/api/health")
def health():
    SYSTEM.ensure_ready()
    assert SYSTEM.index is not None
    return {
        "status": "ok",
        "stats": SYSTEM.index.stats(),
        "evaluation": SYSTEM.eval_metrics,
        "llm": AGENTIC_SYSTEM.llm.safe_config(),
    }


@app.get("/api/config/llm")
def get_llm_config():
    return AGENTIC_SYSTEM.llm.safe_config()


@app.post("/api/config/llm")
def post_llm_config(config: Optional[LLMConfig] = None):
    config = config or LLMConfig()
    provider = config.provider
    base_url = config.base_url.strip()
    model = config.model.strip()
    api_key = config.api_key.strip()

    if provider == "bailian" and not base_url:
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if provider == "bailian" and not model:
        model = "qwen-plus"

    AGENTIC_SYSTEM.llm.configure(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=parse_float(config.timeout),
        enable_thinking=config.enable_thinking,
    )
    return {"status": "ok", "llm": AGENTIC_SYSTEM.llm.safe_config()}


@app.get("/api/config/sources")
def get_sources_config():
    return AGENTIC_SYSTEM.discovery_agent.client.safe_config()


@app.post("/api/config/sources")
def post_sources_config(config: Optional[SourcesConfig] = None):
    config = config or SourcesConfig()
    AGENTIC_SYSTEM.discovery_agent.client.configure(
        semantic_scholar_api_key=config.semantic_scholar_api_key,
        openalex_api_key=config.openalex_api_key,
        openalex_mailto=config.openalex_mailto,
        crossref_mailto=config.crossref_mailto,
        timeout=parse_float(config.timeout),
        per_source_limit=parse_int(config.per_source_limit),
    )
    return {"status": "ok", "sources": AGENTIC_SYSTEM.discovery_agent.client.safe_config()}


@app.get("/api/projects")
def get_projects():
    return {"projects": TASK_STORE.list_projects()}


@app.post("/api/projects")
def post_project(payload: Optional[ProjectPayload] = None):
    payload = payload or ProjectPayload()
    return {"project": TASK_STORE.create_project(payload.name)}


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPayload):
    project = TASK_STORE.update_project(project_id, payload.name)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if project_id == "default":
        raise HTTPException(status_code=400, detail="Default project cannot be deleted")
    if not TASK_STORE.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "ok"}


def parse_archived_filter(value: str = "false") -> bool | None:
    lowered = value.lower()
    if lowered in {"all", "any", "*"}:
        return None
    return lowered not in {"0", "false", "no", ""}


def resolve_conversation_id(value: str) -> str:
    if TASK_STORE.get_conversation(value):
        return value
    task = TASK_STORE.get_task(value, include_result=False)
    if task and task.get("conversation_id"):
        return task["conversation_id"]
    return value


@app.get("/api/tasks")
def get_tasks(project_id: str = "", archived: str = "false", conversation_id: str = ""):
    return {
        "tasks": TASK_STORE.list_tasks(
            project_id or None,
            archived=parse_archived_filter(archived),
            conversation_id=conversation_id or None,
        )
    }


@app.post("/api/tasks")
def post_task(payload: Optional[TaskPayload] = None, stream: str = "false"):
    payload = payload or TaskPayload()
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    task = TASK_STORE.create_task(
        project_id=payload.project_id or "default",
        query=payload.query,
        source_config=task_source_config(payload),
        origin_task_id=payload.origin_task_id,
        conversation_id=payload.conversation_id,
    )
    if stream.lower() not in {"0", "false", "no"}:
        return stream_task(task["id"])
    saved = run_task(task["id"])
    return task_result_envelope(saved)


@app.get("/api/tasks/{task_id_value}")
def get_task(task_id_value: str):
    task = TASK_STORE.get_task(task_id_value, include_result=True)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@app.delete("/api/tasks/{task_id_value}")
def delete_task(task_id_value: str):
    if not TASK_STORE.delete_task(task_id_value):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok"}


@app.post("/api/tasks/{task_id_value}/rerun")
def rerun_task(task_id_value: str, stream: str = "false"):
    task = TASK_STORE.create_rerun_task(task_id_value)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if stream.lower() not in {"0", "false", "no"}:
        return stream_task(task["id"])
    saved = run_task(task["id"])
    return task_result_envelope(saved)


@app.post("/api/tasks/{task_id_value}/move")
def move_task(task_id_value: str, payload: MovePayload):
    task = TASK_STORE.move_task(task_id_value, payload.project_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task or project not found")
    return {"task": task}


@app.post("/api/tasks/{task_id_value}/cancel")
def cancel_task(task_id_value: str):
    task = TASK_STORE.cancel_task(task_id_value)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": TASK_STORE.get_task(task_id_value, include_result=True) or task}


@app.post("/api/tasks/{task_id_value}/archive")
def archive_task(task_id_value: str, payload: Optional[ArchivePayload] = None):
    payload = payload or ArchivePayload()
    task = TASK_STORE.archive_task(task_id_value, archived=payload.archived)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@app.get("/api/conversations")
def get_conversations(archived: str = "false"):
    return {"conversations": TASK_STORE.list_conversations(archived=parse_archived_filter(archived))}


@app.post("/api/conversations")
def post_conversation(payload: Optional[ConversationPayload] = None):
    payload = payload or ConversationPayload()
    return {"conversation": TASK_STORE.create_conversation(payload.title)}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation_id = resolve_conversation_id(conversation_id)
    conversation = TASK_STORE.get_conversation(conversation_id, include_tasks=True)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@app.patch("/api/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, payload: ConversationPayload):
    conversation_id = resolve_conversation_id(conversation_id)
    conversation = TASK_STORE.update_conversation(conversation_id, title=payload.title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    conversation_id = resolve_conversation_id(conversation_id)
    if not TASK_STORE.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@app.post("/api/conversations/{conversation_id}/archive")
@app.patch("/api/conversations/{conversation_id}/archive")
def patch_conversation_archive(conversation_id: str, payload: Optional[ArchivePayload] = None):
    payload = payload or ArchivePayload()
    conversation_id = resolve_conversation_id(conversation_id)
    conversation = TASK_STORE.archive_conversation(conversation_id, archived=payload.archived)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conversation}


@app.get("/api/search")
def search(q: str = "", mode: str = "hybrid", source: str = "", category: str = "", limit: int = 8):
    response = SYSTEM.search(q, mode=mode, source=source, category=category, limit=limit)
    return response.to_dict()


@app.get("/api/metrics")
def metrics():
    SYSTEM.ensure_ready()
    assert SYSTEM.index is not None
    return {
        "stats": SYSTEM.index.stats(),
        "evaluation": SYSTEM.eval_metrics,
        "traces": [t.to_dict() for t in SYSTEM.traces]
    }


@app.get("/api/evaluations/tasks")
def evaluation_tasks():
    return {"tasks": load_eval_tasks(), "metrics": METRIC_DEFINITIONS}


@app.get("/api/status")
def status():
    status_msg = getattr(AGENTIC_SYSTEM, "current_status", "")
    stream_buf = getattr(AGENTIC_SYSTEM, "llm_stream_buffer", "")
    return {"status": status_msg, "stream_buffer": stream_buf}


@app.get("/api/research")
def research_endpoint(q: str = "", online: str = "true", include_local: str = "true", limit: int = 10, stream: str = "false"):
    is_online = online.lower() not in {"0", "false", "no"}
    is_include_local = include_local.lower() not in {"0", "false", "no"}
    payload = TaskPayload(query=q, project_id="default", online=is_online, include_local=is_include_local, limit=limit)
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")
    task = TASK_STORE.create_task(project_id="default", query=q, source_config=task_source_config(payload))
    if stream.lower() not in {"0", "false", "no"}:
        return stream_task(task["id"])
    saved = run_task(task["id"])
    return saved.get("result") or {}


@app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api(full_path: str):
    return Response(status_code=404)


app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="web")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KeyBoy search engine.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    print(f"KeyBoy running at http://{args.host}:{args.port}")
    uvicorn.run("keyboy.app:app", host=args.host, port=args.port, reload=True)

if __name__ == "__main__":
    main()
