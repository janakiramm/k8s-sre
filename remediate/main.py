"""
Agent 2 — Remediate (Google ADK + Gemini)
Receives a diagnosis from Agent 1, applies the fix to the
Kubernetes cluster via MCP, and reports what was changed.
"""

import os
import sys
import json
import logging

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tools import init_mcp, all_tools

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("REMEDIATE_MODEL", "gemini-2.5-flash")
VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [remediate] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent-remediate")

# Suppress noisy third-party loggers
for _name in ("httpx", "httpcore", "google.adk", "google_adk", "google.genai",
              "google_genai", "google.auth", "urllib3", "grpc"):
    logging.getLogger(_name).setLevel(logging.WARNING)

if not GOOGLE_API_KEY:
    log.error("GOOGLE_API_KEY is not set")
    sys.exit(1)

os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY


# --- Agent instruction ---

AGENT_INSTRUCTION = """You are a Kubernetes Remediation Specialist. You receive a diagnosis
from a diagnostic agent and apply the recommended fix to the cluster.

Your methodology:
1. Read the diagnosis carefully to understand the root cause and recommended fix
2. Use `resources_get` to fetch the current state of the affected resource
3. If the resource EXISTS: delete it with `resources_delete`, then create a new
   manifest with the fix applied using `resources_create_or_update`
   If the resource is NOT FOUND: construct a complete manifest from the diagnosis
   details with the fix already applied
4. Use `resources_create_or_update` to apply the corrected manifest
5. Use `pods_list_in_namespace` to confirm the rollout is starting

CRITICAL RULES:
- Always TRY to get the current resource first
- If the resource exists, DELETE it first, then CREATE the fixed version.
  This avoids server-side apply conflicts with field managers.
- If the resource does not exist, create it from scratch using information
  from the diagnosis (container names, images, commands, resource values)
- The YAML you submit must be a complete, valid Kubernetes manifest
- After applying, check that new pods are being created
- Do NOT include status, managedFields, resourceVersion, uid, or other
  server-generated fields in the YAML you submit

Your output must follow this format:

ACTION TAKEN: [What you changed, e.g., "Deleted and recreated deployment/memory-hog with memory limit 512Mi"]
RESOURCE MODIFIED: [e.g., deployment/memory-hog in namespace default]
BEFORE: [Key value before change, e.g., "memory limit: 64Mi"]
AFTER: [Key value after change, e.g., "memory limit: 512Mi"]
ROLLOUT STATUS: [e.g., "New ReplicaSet created, pods starting"]
SUCCESS: [true/false]
"""


# --- Run remediation ---

async def run_remediation(diagnosis: str, namespace: str = "default") -> str:
    log.info("STARTED — model=%s  namespace=%s", MODEL_NAME, namespace)

    init_mcp(MCP_SERVER_URL)

    agent = LlmAgent(
        model=MODEL_NAME,
        name="remediate_agent",
        description="Kubernetes Remediation Specialist that applies fixes to the cluster via MCP.",
        instruction=AGENT_INSTRUCTION,
        tools=all_tools(),
    )

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="k8s-remediate", user_id="orchestrator")
    runner = Runner(agent=agent, app_name="k8s-remediate", session_service=session_service)

    prompt = f"""Apply the recommended fix from the following diagnosis to the Kubernetes cluster.

**Diagnosis from Agent 1:**
{diagnosis}

**Target namespace:** {namespace}

Read the affected resource, apply the fix, and verify the rollout is starting.
If the resource does not exist yet, create it from scratch with the fix already applied.
"""

    result_text = ""
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    async for event in runner.run_async(user_id="orchestrator", session_id=session.id, new_message=message):
        if event.is_final_response():
            for part in event.content.parts:
                if part.text:
                    result_text += part.text
        elif VERBOSE and event.content:
            for part in event.content.parts:
                if part.function_call:
                    log.debug("  Tool call: %s(%s)",
                              part.function_call.name,
                              json.dumps(dict(part.function_call.args or {}))[:100])
                if part.function_response:
                    log.debug("  Tool result: %s", str(part.function_response.response)[:200])

    log.info("COMPLETE")
    return result_text
