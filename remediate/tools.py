"""ADK function tool definitions for the Remediate agent."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.mcp_client import MCPClient


# --- MCP lifecycle ---

_mcp: MCPClient | None = None


def init_mcp(url: str) -> MCPClient:
    global _mcp
    _mcp = MCPClient(url, client_name="agent-remediate")
    _mcp.initialize()
    return _mcp


def close_mcp() -> None:
    if _mcp:
        _mcp.close()


def _call(tool_name: str, args: dict | None = None) -> str:
    if _mcp is None:
        raise RuntimeError("MCP not initialized — call init_mcp() first")
    return _mcp.call_tool(tool_name, args)


# --- ADK function tools ---
# ADK tools are plain functions — docstrings become tool descriptions,
# type hints become parameter schemas.

def resources_create_or_update(resource_yaml: str) -> str:
    """Create or update a Kubernetes resource from a YAML manifest.

    Use this to apply fixes like changing memory limits, updating
    image tags, scaling replicas, or modifying any resource spec.
    The YAML must be a complete, valid Kubernetes resource manifest.

    Args:
        resource_yaml: Complete Kubernetes resource manifest in YAML format.

    Returns:
        Result of the create/update operation.
    """
    return _call("resources_create_or_update", {"resource": resource_yaml})


def resources_get(apiVersion: str, kind: str, name: str, namespace: str) -> str:
    """Get a specific Kubernetes resource by API version, kind, and name.

    Use this to read the current state of a resource before modifying it.

    Args:
        apiVersion: API version, e.g. 'apps/v1'.
        kind: Resource kind, e.g. 'Deployment'.
        name: Name of the resource.
        namespace: Namespace of the resource, e.g. 'default'.

    Returns:
        The full resource manifest as YAML/JSON.
    """
    return _call("resources_get", {"apiVersion": apiVersion, "kind": kind, "name": name, "namespace": namespace})


def pods_list_in_namespace(namespace: str) -> str:
    """List all pods in a Kubernetes namespace.

    Use this to verify pod states after applying a fix.

    Args:
        namespace: Kubernetes namespace to list pods from.

    Returns:
        List of pods with their status.
    """
    return _call("pods_list_in_namespace", {"namespace": namespace})


def resources_delete(apiVersion: str, kind: str, name: str, namespace: str) -> str:
    """Delete a Kubernetes resource by API version, kind, and name.

    Use this to remove a broken resource before recreating it with the fix.

    Args:
        apiVersion: API version, e.g. 'apps/v1'.
        kind: Resource kind, e.g. 'Deployment'.
        name: Name of the resource.
        namespace: Namespace of the resource, e.g. 'default'.

    Returns:
        Result of the delete operation.
    """
    return _call("resources_delete", {"apiVersion": apiVersion, "kind": kind, "name": name, "namespace": namespace})


def all_tools() -> list:
    return [resources_create_or_update, resources_get, resources_delete, pods_list_in_namespace]
