"""Strands tool definitions for the Verify agent."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strands import tool
from shared.mcp_client import MCPClient


# --- MCP lifecycle ---

_mcp: MCPClient | None = None


def init_mcp(url: str) -> MCPClient:
    global _mcp
    _mcp = MCPClient(url, client_name="agent-verify")
    _mcp.initialize()
    return _mcp


def close_mcp() -> None:
    if _mcp:
        _mcp.close()


def _call(tool_name: str, args: dict | None = None) -> str:
    if _mcp is None:
        raise RuntimeError("MCP not initialized — call init_mcp() first")
    return _mcp.call_tool(tool_name, args)


# --- Strands tools (read-only, for verification) ---

@tool
def pods_list_in_namespace(namespace: str) -> str:
    """List all pods in a Kubernetes namespace.

    Returns pod names, status, restarts, and age. Use this to check
    whether pods are Running or still in CrashLoopBackOff/OOMKilled.

    Args:
        namespace: Kubernetes namespace to list pods from.
    """
    return _call("pods_list_in_namespace", {"namespace": namespace})


@tool
def pods_get(name: str, namespace: str) -> str:
    """Get detailed information about a specific pod.

    Returns status, container states, restart counts, and termination
    reasons. Use this to verify a specific pod is healthy after remediation.

    Args:
        name: Name of the pod to inspect.
        namespace: Namespace of the pod.
    """
    return _call("pods_get", {"name": name, "namespace": namespace})


@tool
def events_list(namespace: str) -> str:
    """List recent Kubernetes events in a namespace.

    Events show warnings, errors, and state changes like OOMKilled,
    FailedScheduling, BackOff, etc. Use this to check for new problems
    after remediation.

    Args:
        namespace: Namespace to list events from.
    """
    return _call("events_list", {"namespace": namespace})


def all_tools() -> list:
    return [pods_list_in_namespace, pods_get, events_list]
