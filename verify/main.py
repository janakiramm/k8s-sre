"""
Agent 3 — Verify (Strands Agents + Anthropic Claude)
Receives a remediation report from Agent 2 and verifies that the
fix actually worked by checking pod status and cluster events.
"""

import os
import sys
import logging
import warnings

from strands import Agent
from strands.models.anthropic import AnthropicModel

from tools import init_mcp, all_tools

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("VERIFY_MODEL", "claude-sonnet-4-20250514")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [verify] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent-verify")

# Suppress noisy third-party loggers
for _name in ("httpx", "httpcore", "anthropic", "strands", "urllib3"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# Suppress Pydantic serialization warnings from Strands/Anthropic SDK
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

if not ANTHROPIC_API_KEY:
    log.error("ANTHROPIC_API_KEY is not set")
    sys.exit(1)


# --- Agent system prompt ---

SYSTEM_PROMPT = """You are a Kubernetes Verification Specialist. You receive a remediation
report describing a fix that was applied to the cluster. Your job is to verify
that the fix actually worked.

Your methodology:
1. Use `pods_list_in_namespace` to list all pods and check their status
2. Use `pods_get` on specific pods to inspect container states, restart counts,
   and termination reasons
3. Use `events_list` to check for recent warnings or errors

What to look for:
- All pods for the affected deployment should be in Running status
- No containers should be in CrashLoopBackOff or OOMKilled state
- Restart counts should be stable (not increasing)
- No recent warning events related to the affected deployment
- The expected number of replicas should be running

Your output must follow this format:

PODS HEALTHY: [true/false]
DEPLOYMENT: [e.g., deployment/memory-hog in namespace default]
POD STATUS:
- [pod-name]: [status] (restarts: N)
- [pod-name]: [status] (restarts: N)
RECENT EVENTS: [Summary of relevant events, or "No warning events"]
DETAILS: [One-line summary, e.g., "3/3 pods Running, 0 OOMKilled events in last 60s"]
VERDICT: [RESOLVED / NOT RESOLVED / PARTIALLY RESOLVED]
"""


# --- Run verification ---

def run_verification(remediation_report: str, namespace: str = "default") -> str:
    log.info("STARTED — model=%s  namespace=%s", MODEL_NAME, namespace)

    init_mcp(MCP_SERVER_URL)

    model = AnthropicModel(
        client_args={"api_key": ANTHROPIC_API_KEY},
        model_id=MODEL_NAME,
        max_tokens=4096,
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=all_tools(),
        callback_handler=None,
    )

    prompt = f"""Verify that the following remediation was successful by checking the cluster state.

**Remediation Report from Agent 2:**
{remediation_report}

**Target namespace:** {namespace}

Check pod status, container states, and recent events. Report whether the fix worked.
"""

    result = agent(prompt)

    log.info("COMPLETE")
    return str(result)
