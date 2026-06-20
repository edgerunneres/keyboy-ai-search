from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agentic import AgenticKeyBoySystem
from .agents import KeyBoySystem


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
SYSTEM = KeyBoySystem()
AGENTIC_SYSTEM = AgenticKeyBoySystem()


class KeyBoyHandler(BaseHTTPRequestHandler):
    server_version = "KeyBoy/2.0"

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _static(self, relative: str) -> None:
        target = (WEB_ROOT / relative.lstrip("/")).resolve()
        if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/health":
            SYSTEM.ensure_ready()
            assert SYSTEM.index is not None
            self._json(
                {
                    "status": "ok",
                    "stats": SYSTEM.index.stats(),
                    "evaluation": SYSTEM.eval_metrics,
                    "llm": AGENTIC_SYSTEM.llm.safe_config(),
                }
            )
            return
        if parsed.path == "/api/config/llm":
            self._json(AGENTIC_SYSTEM.llm.safe_config())
            return
        if parsed.path == "/api/config/sources":
            self._json(AGENTIC_SYSTEM.discovery_agent.client.safe_config())
            return
        if parsed.path == "/api/search":
            q = query.get("q", [""])[0]
            mode = query.get("mode", ["hybrid"])[0]
            source = query.get("source", [""])[0]
            category = query.get("category", [""])[0]
            limit = int(query.get("limit", ["8"])[0])
            response = SYSTEM.search(q, mode=mode, source=source, category=category, limit=limit)
            self._json(response.to_dict())
            return
        if parsed.path == "/api/research":
            q = query.get("q", [""])[0]
            online = query.get("online", ["true"])[0].lower() not in {"0", "false", "no"}
            include_local = query.get("include_local", ["true"])[0].lower() not in {"0", "false", "no"}
            limit = int(query.get("limit", ["10"])[0])
            response = AGENTIC_SYSTEM.research(q, online=online, include_local=include_local, limit=limit)
            self._json(response.to_dict())
            return
        if parsed.path == "/api/metrics":
            SYSTEM.ensure_ready()
            assert SYSTEM.index is not None
            self._json({"stats": SYSTEM.index.stats(), "evaluation": SYSTEM.eval_metrics, "traces": [t.to_dict() for t in SYSTEM.traces]})
            return
        self._static("index.html" if parsed.path == "/" else parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config/llm":
            payload = self._read_json()
            provider = str(payload.get("provider") or "bailian")
            base_url = str(payload.get("base_url") or "").strip()
            model = str(payload.get("model") or "").strip()
            api_key = str(payload.get("api_key") or "").strip()
            timeout_value = payload.get("timeout")
            timeout = None
            if timeout_value not in (None, ""):
                try:
                    timeout = float(timeout_value)
                except (TypeError, ValueError):
                    timeout = None
            if provider == "bailian" and not base_url:
                base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            if provider == "bailian" and not model:
                model = "qwen-plus"
            AGENTIC_SYSTEM.llm.configure(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=timeout,
                enable_thinking=bool(payload.get("enable_thinking")),
            )
            self._json({"status": "ok", "llm": AGENTIC_SYSTEM.llm.safe_config()})
            return
        if parsed.path == "/api/config/sources":
            payload = self._read_json()
            timeout = None
            per_source_limit = None
            if payload.get("timeout") not in (None, ""):
                try:
                    timeout = float(payload.get("timeout"))
                except (TypeError, ValueError):
                    timeout = None
            if payload.get("per_source_limit") not in (None, ""):
                try:
                    per_source_limit = int(payload.get("per_source_limit"))
                except (TypeError, ValueError):
                    per_source_limit = None
            AGENTIC_SYSTEM.discovery_agent.client.configure(
                semantic_scholar_api_key=str(payload.get("semantic_scholar_api_key") or ""),
                openalex_api_key=str(payload.get("openalex_api_key") or ""),
                openalex_mailto=str(payload.get("openalex_mailto") or ""),
                crossref_mailto=str(payload.get("crossref_mailto") or ""),
                timeout=timeout,
                per_source_limit=per_source_limit,
            )
            self._json({"status": "ok", "sources": AGENTIC_SYSTEM.discovery_agent.client.safe_config()})
            return
        self.send_error(HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KeyBoy search engine.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()
    SYSTEM.bootstrap()
    server = ThreadingHTTPServer((args.host, args.port), KeyBoyHandler)
    print(f"KeyBoy running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
