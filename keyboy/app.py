from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import KeyBoySystem


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
SYSTEM = KeyBoySystem()


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
            self._json({"status": "ok", "stats": SYSTEM.index.stats(), "evaluation": SYSTEM.eval_metrics})
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
        if parsed.path == "/api/metrics":
            SYSTEM.ensure_ready()
            assert SYSTEM.index is not None
            self._json({"stats": SYSTEM.index.stats(), "evaluation": SYSTEM.eval_metrics, "traces": [t.to_dict() for t in SYSTEM.traces]})
            return
        self._static("index.html" if parsed.path == "/" else parsed.path)


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

