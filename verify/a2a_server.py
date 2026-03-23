"""A2A server wrapper for the Verify agent (port 10003)."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import run_verification
from tools import close_mcp
from shared.a2a_server import start_a2a_server

PORT = int(os.getenv("VERIFY_PORT", "10003"))

AGENT_CARD = {
    "name": "Kubernetes Verify Agent",
    "description": "Verifies that a remediation was successful by checking pod status and cluster events.",
    "url": f"http://localhost:{PORT}",
    "version": "1.0",
    "capabilities": ["kubernetes_verification"],
    "input_modes": ["text"],
    "output_modes": ["text"],
}

if __name__ == "__main__":
    start_a2a_server(
        agent_card=AGENT_CARD,
        run_fn=run_verification,
        port=PORT,
        cleanup_fn=close_mcp,
    )
