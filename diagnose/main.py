"""
Agent 1 — Diagnose (CrewAI + GPT-5)
Investigates Kubernetes pod failures via MCP tools and produces
a structured diagnosis with root cause, evidence, and recommended fix.
"""

import os
import sys
import logging

from crewai import Agent, Task, Crew, Process, LLM
from crewai.utilities.printer import Printer

from tools import init_mcp, all_tools

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080/mcp")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("DIAGNOSE_MODEL", "openai/gpt-4.1")
VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

# --- Logging setup ---
# Use basicConfig at WARNING to silence CrewAI's root-level logging.info() calls
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-7s  [diagnose] %(message)s",
    datefmt="%H:%M:%S",
)
# Own logger with dedicated handler (CrewAI logs via root, so propagate=False keeps it clean)
log = logging.getLogger("agent-diagnose")
log.setLevel(logging.INFO)
log.propagate = False
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    "%(asctime)s  %(levelname)-7s  [diagnose] %(message)s", datefmt="%H:%M:%S"))
log.addHandler(_handler)

# Suppress noisy third-party loggers
for _name in ("httpx", "httpcore", "openai", "crewai", "crewai.crew",
              "crewai.agent", "crewai.utilities", "litellm", "urllib3"):
    logging.getLogger(_name).setLevel(logging.WARNING)

# Silence CrewAI's Printer (direct console output like "Repaired JSON")
Printer.print = lambda self, *args, **kwargs: None

if not OPENAI_API_KEY:
    log.error("OPENAI_API_KEY is not set")
    sys.exit(1)

llm = LLM(model=MODEL_NAME, api_key=OPENAI_API_KEY)


# --- Agent prompts ---

AGENT_BACKSTORY = """You are an expert Kubernetes SRE. You diagnose pod failures quickly
using the minimum number of tool calls.

IMPORTANT: When using tools, provide the Action Input as a single flat JSON object
(e.g. {"namespace": "default"}). Never use a list/array as input.

If a tool call fails, skip it and work with what you have.
Be efficient — 2-3 tool calls are usually enough to diagnose an issue.

When recommending memory/CPU fixes, always add a 2x safety margin above the
application's actual usage. For example, if a container allocates 256MB, recommend
at least 512Mi to account for runtime overhead.
"""

TASK_TEMPLATE = """Diagnose the following Kubernetes issue.

**Problem:** {problem_report}

**Steps (use only what you need):**
1. `pods_list_in_namespace` with namespace `{namespace}` to find failing pods
2. `pods_get` on one failing pod to see container states and resource limits
3. If needed, `events_list` for cluster-level context

Then produce your diagnosis. Do NOT call more tools than necessary.

**Output format:**
ROOT CAUSE: [one line]
AFFECTED RESOURCE: [e.g., deployment/memory-hog in namespace default]
EVIDENCE:
- [key finding 1]
- [key finding 2]
RECOMMENDED FIX: [specific action, e.g., "Increase memory limit from 64Mi to 512Mi"]
CONFIDENCE: [high/medium/low]
"""

EXPECTED_OUTPUT = """ROOT CAUSE, AFFECTED RESOURCE, EVIDENCE, RECOMMENDED FIX, CONFIDENCE."""


# --- Run diagnosis ---

def run_diagnosis(problem_report: str, namespace: str = "default") -> str:
    log.info("STARTED — model=%s  namespace=%s", MODEL_NAME, namespace)

    init_mcp(MCP_SERVER_URL)
    steps = [0]

    def _on_step(step_output):
        steps[0] += 1
        tool = getattr(step_output, "tool", None)
        if tool:
            log.info("  step %d — tool: %s", steps[0], tool)
        else:
            log.info("  step %d — reasoning", steps[0])

    agent = Agent(
        role="Kubernetes Diagnostics Specialist",
        goal="Investigate Kubernetes pod failures via MCP tools. Identify root cause and recommend a fix.",
        backstory=AGENT_BACKSTORY,
        tools=all_tools(),
        llm=llm,
        verbose=VERBOSE,
        max_iter=6,
        allow_delegation=False,
        step_callback=_on_step,
    )

    task = Task(
        description=TASK_TEMPLATE.format(problem_report=problem_report, namespace=namespace),
        expected_output=EXPECTED_OUTPUT,
        agent=agent,
    )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=VERBOSE)

    try:
        result = crew.kickoff()
    except Exception as exc:
        log.error("FAILED: %s", exc)
        return f"Diagnosis failed: {exc}"

    log.info("COMPLETE")
    return str(result)
