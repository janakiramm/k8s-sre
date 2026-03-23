"""
Shared MCP Streamable HTTP client.

Talks to a Kubernetes MCP server over JSON-RPC with session management:
  initialize → notifications/initialized → tools/call
"""

import json
import logging

import httpx


class MCPClient:
    """Minimal MCP Streamable HTTP client with session management."""

    def __init__(self, url: str, client_name: str = "mcp-client"):
        self.url = url
        self.session_id: str | None = None
        self._client_name = client_name
        self._call_id = 0
        self._log = logging.getLogger(client_name)
        self._http = httpx.Client(timeout=60.0)
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _next_id(self) -> int:
        self._call_id += 1
        return self._call_id

    def _session_headers(self) -> dict:
        headers = dict(self._headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _capture_session_id(self, resp: httpx.Response) -> None:
        sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid

    def _parse_sse_response(self, text: str) -> dict | None:
        result = None
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    result = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
        return result

    def _send(self, payload: dict) -> dict:
        resp = self._http.post(self.url, json=payload, headers=self._session_headers())
        resp.raise_for_status()
        self._capture_session_id(resp)

        if not resp.text or not resp.text.strip():
            return {}

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            data = self._parse_sse_response(resp.text)
            if data is None:
                raise ValueError(f"Unparseable SSE response: {resp.text[:200]}")
            return data
        return resp.json()

    def _notify(self, payload: dict) -> None:
        resp = self._http.post(self.url, json=payload, headers=self._session_headers())
        if resp.status_code not in (200, 202, 204):
            resp.raise_for_status()
        self._capture_session_id(resp)

    def initialize(self) -> None:
        self._log.debug("MCP handshake: initialize...")
        init_resp = self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": self._client_name, "version": "1.0.0"},
            },
        })
        if "error" in init_resp:
            raise RuntimeError(f"MCP initialize failed: {init_resp['error']}")

        server_info = init_resp.get("result", {}).get("serverInfo", {})
        self._log.debug("MCP server: %s v%s (session: %s)",
                        server_info.get("name", "unknown"),
                        server_info.get("version", "?"),
                        self.session_id)

        self._notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._log.debug("MCP connected to %s", self.url)

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> str:
        if self.session_id is None:
            self.initialize()

        data = self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        })

        if "error" in data:
            return f"MCP error: {data['error'].get('message', data['error'])}"

        content = data.get("result", {}).get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if texts else json.dumps(data.get("result", {}), indent=2)

    def close(self) -> None:
        self._http.close()
