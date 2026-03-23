"""CrewAI tool definitions for the Diagnose agent."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from shared.mcp_client import MCPClient


# --- MCP lifecycle ---

_mcp: MCPClient | None = None


def init_mcp(url: str) -> MCPClient:
    global _mcp
    _mcp = MCPClient(url, client_name="agent-diagnose")
    _mcp.initialize()
    return _mcp


def close_mcp() -> None:
    if _mcp:
        _mcp.close()


def _call(tool_name: str, args: dict | None = None) -> str:
    if _mcp is None:
        raise RuntimeError("MCP not initialized — call init_mcp() first")
    return _mcp.call_tool(tool_name, args)


# --- CrewAI tools ---

class PodsListInput(BaseModel):
    namespace: str = Field(description="Kubernetes namespace to list pods from")

class PodsListTool(BaseTool):
    name: str = "pods_list_in_namespace"
    description: str = "List all pods in a Kubernetes namespace. Returns pod names, status, restarts, and age."
    args_schema: type[BaseModel] = PodsListInput

    def _run(self, namespace: str) -> str:
        return _call("pods_list_in_namespace", {"namespace": namespace})


class PodsGetInput(BaseModel):
    name: str = Field(description="Name of the pod to get")
    namespace: str = Field(description="Namespace of the pod")

class PodsGetTool(BaseTool):
    name: str = "pods_get"
    description: str = "Get detailed pod info including status, container states, restart counts, and termination reasons."
    args_schema: type[BaseModel] = PodsGetInput

    def _run(self, name: str, namespace: str) -> str:
        return _call("pods_get", {"name": name, "namespace": namespace})


class PodsLogInput(BaseModel):
    name: str = Field(description="Name of the pod")
    namespace: str = Field(description="Namespace of the pod")
    container: str | None = Field(default=None, description="Container name (optional)")
    previous: bool = Field(default=False, description="Get logs from previous terminated container")

class PodsLogTool(BaseTool):
    name: str = "pods_log"
    description: str = "Get pod logs. Use previous=true for logs from a terminated container (useful for OOMKilled)."
    args_schema: type[BaseModel] = PodsLogInput

    def _run(self, name: str, namespace: str, container: str | None = None, previous: bool = False) -> str:
        args = {"name": name, "namespace": namespace}
        if container:
            args["container"] = container
        if previous:
            args["previous"] = True
        return _call("pods_log", args)


class EventsListInput(BaseModel):
    namespace: str | None = Field(default=None, description="Namespace to filter events (optional)")

class EventsListTool(BaseTool):
    name: str = "events_list"
    description: str = "List Kubernetes events — warnings, errors, OOMKilled, FailedScheduling, BackOff, etc."
    args_schema: type[BaseModel] = EventsListInput

    def _run(self, namespace: str | None = None) -> str:
        args = {"namespace": namespace} if namespace else {}
        return _call("events_list", args)


class ResourcesGetInput(BaseModel):
    apiVersion: str = Field(description="API version, e.g. 'apps/v1'")
    kind: str = Field(description="Resource kind, e.g. 'Deployment'")
    name: str = Field(description="Resource name")
    namespace: str | None = Field(default=None, description="Namespace (optional)")

class ResourcesGetTool(BaseTool):
    name: str = "resources_get"
    description: str = "Get a Kubernetes resource by API version, kind, and name. Use to inspect Deployment specs, limits, etc."
    args_schema: type[BaseModel] = ResourcesGetInput

    def _run(self, apiVersion: str, kind: str, name: str, namespace: str | None = None) -> str:
        args = {"apiVersion": apiVersion, "kind": kind, "name": name}
        if namespace:
            args["namespace"] = namespace
        return _call("resources_get", args)


def all_tools() -> list[BaseTool]:
    return [PodsListTool(), PodsGetTool(), PodsLogTool(), EventsListTool(), ResourcesGetTool()]
