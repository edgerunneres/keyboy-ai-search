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
from fastapi import FastAPI

from .agentic import AgenticKeyBoySystem
from .agents import KeyBoySystem


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
SYSTEM = KeyBoySystem()
AGENTIC_SYSTEM = AgenticKeyBoySystem()

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


@app.on_event("startup")
def startup_event():
    SYSTEM.bootstrap()


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


@app.get("/api/status")
def status():
    status_msg = getattr(AGENTIC_SYSTEM, "current_status", "")
    stream_buf = getattr(AGENTIC_SYSTEM, "llm_stream_buffer", "")
    return {"status": status_msg, "stream_buffer": stream_buf}


@app.get("/api/research")
def research_endpoint(q: str = "", online: str = "true", include_local: str = "true", limit: int = 10, stream: str = "false"):
    is_online = online.lower() not in {"0", "false", "no"}
    is_include_local = include_local.lower() not in {"0", "false", "no"}

    if stream.lower() not in {"0", "false", "no"}:
        q_queue = queue.Queue()

        def run_research():
            try:
                result = AGENTIC_SYSTEM.research(q, online=is_online, include_local=is_include_local, limit=limit, on_event=q_queue.put)
                q_queue.put({"type": "complete", "result": result.to_dict()})
            except Exception as e:
                q_queue.put({"type": "error", "message": str(e)})
            finally:
                q_queue.put(None)

        threading.Thread(target=run_research).start()

        def event_generator():
            while True:
                event = q_queue.get()
                if event is None:
                    break
                yield {"data": json.dumps(event, ensure_ascii=False)}

        return EventSourceResponse(event_generator())
    else:
        response = AGENTIC_SYSTEM.research(q, online=is_online, include_local=is_include_local, limit=limit)
        return response.to_dict()


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
