# Agentic AI Meets Kubernetes

**KubeAuto Day Europe 2026 — Amsterdam, 23 March**

Three autonomous AI agents diagnose, fix, and verify a broken Kubernetes deployment. Each agent uses a different framework and LLM, all connected through a single MCP server and communicating via the A2A protocol.

```
Orchestrator (Python, Watch API + A2A client)
    │
    ├── Agent 1 — Diagnose   (CrewAI + GPT-5)
    ├── Agent 2 — Remediate  (Google ADK + Gemini)
    └── Agent 3 — Verify     (Strands + Claude)
```

Four components. Three frameworks. Three LLMs. One MCP server. One protocol.

---

## Project Structure

```
.
├── shared/                  # Shared modules used by all agents
│   ├── mcp_client.py        # MCP Streamable HTTP client (JSON-RPC)
│   ├── a2a_server.py        # A2A server base class
│   └── a2a_types.py         # A2A protocol types
├── diagnose/                # Agent 1 — CrewAI + GPT-5
│   ├── main.py              # Agent logic and tools
│   ├── tools.py             # MCP-backed diagnostic tools
│   └── a2a_server.py        # A2A endpoint
├── remediate/               # Agent 2 — Google ADK + Gemini
│   ├── main.py              # Agent logic and tools
│   ├── tools.py             # MCP-backed remediation tools
│   └── a2a_server.py        # A2A endpoint
├── verify/                  # Agent 3 — Strands + Claude
│   ├── main.py              # Agent logic and tools
│   ├── tools.py             # MCP-backed verification tools
│   └── a2a_server.py        # A2A endpoint
├── orchestrator/            # Lightweight orchestrator (no LLM)
│   ├── main.py              # Watch API + A2A dispatch
│   └── a2a_client.py        # A2A client for calling agents
├── MCP/                     # Kubernetes MCP server setup
│   ├── setup.sh             # Helm install script
│   └── mcp-values.yaml      # Helm values
├── workload/
│   └── mem-hog.yaml         # Demo deployment (OOMKilled scenario)
└── requirements.txt         # Python dependencies
```

---

## Prerequisites

- Python 3.12+
- A running Kubernetes cluster (Minikube recommended)
- `kubectl` configured and pointing to the cluster
- Helm 3
- API keys for OpenAI, Google AI, and Anthropic

---

## Step 1 — Install the MCP Server

The Kubernetes MCP server runs inside the cluster and exposes tools over Streamable HTTP.

```bash
cd MCP
bash setup.sh
```

This installs the Helm chart into the `mcp` namespace with `edit` ClusterRole binding.

Start the port-forward (keep this terminal open throughout the demo):

```bash
kubectl port-forward -n mcp svc/kubernetes-mcp-server 8080:8080
```

Verify it is running:

```bash
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}'
```

You should see a JSON response with `serverInfo`.

Run the MCP Inspector.

```bash
npx -y @modelcontextprotocol/inspector@latest
```

---

## Step 2 — Install Python Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 3 — Set Environment Variables

```bash
export OPENAI_API_KEY="sk-..."        # For Agent 1 (Diagnose)
export GOOGLE_API_KEY="AIza..."       # For Agent 2 (Remediate)
export ANTHROPIC_API_KEY="sk-ant-..." # For Agent 3 (Verify)
```

---

## Step 4 — Deploy the Broken Workload

```bash
kubectl apply -f workload/mem-hog.yaml
```

This creates a Deployment with 3 replicas. Each pod tries to allocate 256Mi of memory inside a container limited to 64Mi, triggering an immediate OOMKill and CrashLoopBackOff.

Confirm the pods are crashing:

```bash
kubectl get pods -w
```

---

## Step 5 — Start the Agents (Three Terminals)

Each agent runs as an A2A server on a separate port.

**Terminal 2 — Diagnose (port 10001):**

```bash
python diagnose/a2a_server.py
```

**Terminal 3 — Remediate (port 10002):**

```bash
python remediate/a2a_server.py
```

**Terminal 4 — Verify (port 10003):**

```bash
python verify/a2a_server.py
```

```bash
curl localhost:10001/.well-known/agent.json
```

---

## Step 6 — Run the Orchestrator

```bash
python orchestrator/main.py
```

The orchestrator watches for pod failures via the Kubernetes Watch API. When it detects a CrashLoopBackOff or OOMKilled event, it triggers the pipeline:

1. **Diagnose** — Agent 1 investigates pod status, logs, and events to identify root cause
2. **Remediate** — Agent 2 receives the diagnosis, deletes the broken deployment, and creates a corrected version with increased memory limits
3. **Verify** — Agent 3 checks that new pods are running and healthy

---

## Running Agents Individually

You can also test each agent standalone without the orchestrator.

**Diagnose:**

```bash
python diagnose/main.py
```

**Remediate (paste diagnosis, then Ctrl+D):**

```bash
python remediate/main.py
```

**Verify (paste remediation report, then Ctrl+D):**

```bash
python verify/main.py
```

Or pipe them together:

```bash
python diagnose/main.py | python remediate/main.py | python verify/main.py
```

---

## Demo Scenario Summary

| Phase | Agent | Framework | LLM | What Happens |
| --- | --- | --- | --- | --- |
| Diagnose | Agent 1 | CrewAI | GPT-5 | Lists pods, reads status, checks events, identifies OOMKilled root cause |
| Remediate | Agent 2 | Google ADK | Gemini 2.5 Flash | Fetches deployment, deletes it, recreates with 512Mi memory limit |
| Verify | Agent 3 | Strands | Claude | Confirms pods are running, no OOMKills, deployment healthy |

---

## Key Design Decisions

**Why not use the MCP SDK adapters**?Both CrewAI's `MCPServerAdapter` and ADK's `McpToolset` had issues. CrewAI passed `None`schemas that broke GPT-5 function calling. ADK had async session management bugs. All agents use a shared `MCPClient` class (`shared/mcp_client.py`) that calls the MCP server directly via JSON-RPC over Streamable HTTP. Full control, no surprises.

**Why delete and recreate instead of patching**?The Kubernetes MCP server uses server-side apply. Resources created with `kubectl apply`(client-side) have a different field manager, causing conflicts on update. Delete and recreate avoids this cleanly.

**Why is the orchestrator not an agent**?Not everything needs to be an agent. The orchestrator is a simple Python loop that watches for problems and dispatches tasks. It saves money and latency by keeping the LLM out of the coordination layer.

---

## Troubleshooting

**MCP connection refused** — Make sure the port-forward is running in a separate terminal.

**Agent gives up when resource not found** — The remediate agent handles this. It will create the deployment from scratch using details in the diagnosis.

**Field manager conflict on apply** — The agent uses delete + recreate to avoid this.

**"Default value is not supported" warning** — Harmless. Gemini's function calling API does not support default parameter values. All tool parameters are required.