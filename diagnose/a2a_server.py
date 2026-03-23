"""A2A server wrapper for the Diagnose agent (port 10001)."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import run_diagnosis
from tools import close_mcp
from shared.a2a_server import start_a2a_server

PORT = int(os.getenv("DIAGNOSE_PORT", "10001"))

AGENT_CARD = {
    "name": "Kubernetes Diagnose Agent",
    "description": "Investigates Kubernetes pod failures and produces a structured diagnosis.",
    "url": f"http://localhost:{PORT}",
    "version": "1.0",
    "capabilities": ["kubernetes_diagnosis"],
    "input_modes": ["text"],
    "output_modes": ["text"],
}

if __name__ == "__main__":
    start_a2a_server(
        agent_card=AGENT_CARD,
        run_fn=run_diagnosis,
        port=PORT,
        cleanup_fn=close_mcp,
    )
