"""
Shared A2A server — reusable HTTP handler for wrapping any agent.

Usage:
    start_a2a_server(
        agent_card={"name": "My Agent", ...},
        run_fn=my_run_function,        # str -> str
        port=10001,
    )
"""

import asyncio
import json
import logging
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

log = logging.getLogger("a2a-server")


def _make_handler(
    agent_card: dict,
    run_fn: Callable[[str, str], str],
    cleanup_fn: Callable[[], None] | None = None,
    is_async: bool = False,
    namespace: str = "default",
) -> type[BaseHTTPRequestHandler]:
    """Create an A2A HTTP request handler class."""

    class A2AHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/.well-known/agent.json":
                body = json.dumps(agent_card).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        def do_POST(self):
            if self.path != "/tasks/send":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            task_id = body.get("id", str(uuid.uuid4()))
            message = body["params"]["message"]["parts"][0]["text"]

            try:
                if is_async:
                    output = asyncio.run(run_fn(message, namespace))
                else:
                    output = run_fn(message, namespace)
                status = "completed"
                error = None
            except Exception as exc:
                log.error("Agent failed: %s", exc)
                output = ""
                status = "failed"
                error = str(exc)
            finally:
                if cleanup_fn:
                    cleanup_fn()

            response = {
                "jsonrpc": "2.0",
                "id": task_id,
                "result": {
                    "id": task_id,
                    "status": {"state": status},
                    "artifacts": [{"parts": [{"type": "text", "text": output}]}],
                },
            }
            if error:
                response["result"]["error"] = error

            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(encoded)

    return A2AHandler


def start_a2a_server(
    agent_card: dict,
    run_fn: Callable[[str, str], str],
    port: int,
    *,
    cleanup_fn: Callable[[], None] | None = None,
    is_async: bool = False,
    namespace: str = "default",
) -> None:
    """Start an A2A HTTP server for the given agent."""
    handler = _make_handler(agent_card, run_fn, cleanup_fn, is_async, namespace)
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"[{agent_card['name']}] A2A server running on port {port}")
    server.serve_forever()
