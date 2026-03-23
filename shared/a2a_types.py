# shared/a2a_types.py
from dataclasses import dataclass, field
from typing import Any, Optional
import uuid


@dataclass
class AgentCard:
    """Agent Card — advertises agent capabilities (fetched from /.well-known/agent.json)"""
    name: str
    description: str
    url: str                        # Base URL of the A2A server
    version: str = "1.0"
    capabilities: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["text"])
    output_modes: list[str] = field(default_factory=lambda: ["text"])


@dataclass
class A2ATask:
    """Represents a unit of work sent from host → remote agent"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class A2AResult:
    """Response returned from remote agent → host"""
    task_id: str
    status: str          # "completed" | "failed" | "in_progress"
    output: str = ""
    error: Optional[str] = None
