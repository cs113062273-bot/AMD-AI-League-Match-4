"""Actual HTTP integration fixture server, including faults. No production interception."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import json
import threading
import time


class FakeWeb:
    def __init__(self, routes):
        self.routes = routes
        self.hits = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return
            def do_GET(self):
                owner.hits.append(self.path)
                route = owner.routes.get(self.path, (404, "text/plain", b"not found"))
                if callable(route):
                    route = route(self.path, owner.hits)
                status, ct, body, *extras = route
                headers = extras[0] if extras else {}
                if "X-Delay" in headers:
                    time.sleep(float(headers["X-Delay"]))
                if isinstance(body, str):
                    body = body.encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(body)))
                    for k, v in headers.items():
                        if not k.startswith("X-"):
                            self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
