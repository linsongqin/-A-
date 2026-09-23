from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from src.qa import answer_question


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"


class Handler(BaseHTTPRequestHandler):
    server_version = "FinancialReportRAG/1.0"

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self.send_json({"ok": True, "corpus": "12家白酒公司·2025年报", "retrieval": "Vector + BM25 + RRF"})
            return
        requested = WEB_DIR / ("index.html" if path == "/" else path.lstrip("/"))
        if not requested.exists() or not requested.is_file() or WEB_DIR not in requested.resolve().parents:
            self.send_error(404)
            return
        content = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(requested))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/ask":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            question = str(payload.get("question", "")).strip()
            if not question:
                self.send_json({"error": "请输入问题"}, 400)
                return
            result = answer_question(question, top_k=int(payload.get("top_k", 8)))
            self.send_json(result)
        except Exception as exc:
            self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="启动财报混合检索问答页面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"财报问答页面：http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

