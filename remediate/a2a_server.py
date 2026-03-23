"""A2A server wrapper for the Remediate agent (port 10002)."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import run_remediation
from tools import close_mcp
from shared.a2a_server import start_a2a_server

PORT = int(os.getenv("REMEDIATE_PORT", "10002"))

AGENT_CARD = {
    "name": "Kubernetes Remediate Agent",
    "description": "Receives a diagnosis and applies the recommended fix to the Kubernetes cluster.",
    "url": f"http://localhost:{PORT}",
    "version": "1.0",
    "capabilities": ["kubernetes_remediation"],
    "input_modes": ["text"],
    "output_modes": ["text"],
}

if __name__ == "__main__":
    start_a2a_server(
        agent_card=AGENT_CARD,
        run_fn=run_remediation,
        port=PORT,
        cleanup_fn=close_mcp,
        is_async=True,
    )
