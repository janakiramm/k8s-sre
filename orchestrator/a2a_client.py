"""Lightweight A2A client — discovers agents and sends tasks."""

import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.a2a_types import AgentCard, A2ATask, A2AResult

# Default timeout for agent calls (seconds).
# Agents need time for multiple LLM round-trips + MCP tool calls.
DEFAULT_TIMEOUT = 300


class A2AClient:
    def __init__(self, agent_base_url: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = agent_base_url.rstrip("/")
        self.timeout = timeout
        self.agent_card: AgentCard | None = None

    def discover(self) -> AgentCard:
        """Fetch Agent Card from /.well-known/agent.json"""
        url = f"{self.base_url}/.well-known/agent.json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        self.agent_card = AgentCard(**data)
        return self.agent_card

    def send_task(self, task: A2ATask) -> A2AResult:
        """Send a task to the remote agent via JSON-RPC."""
        payload = {
            "jsonrpc": "2.0",
            "id": task.id,
            "method": "tasks/send",
            "params": {
                "id": task.id,
                "sessionId": task.session_id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": task.message}],
                },
            },
        }
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/tasks/send",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read())
            status = result["result"]["status"]["state"]
            artifacts = result["result"].get("artifacts", [])
            text = artifacts[0]["parts"][0]["text"] if artifacts else ""
            error = result["result"].get("error")
            return A2AResult(task_id=task.id, status=status, output=text, error=error)
        except urllib.error.URLError as e:
            return A2AResult(task_id=task.id, status="failed", error=f"Connection error: {e}")
        except TimeoutError:
            return A2AResult(task_id=task.id, status="failed", error=f"Timeout after {self.timeout}s")


def send_message(client: A2AClient, message: str) -> A2AResult:
    """Convenience: send a text message and return the result."""
    task = A2ATask(message=message)
    return client.send_task(task)
