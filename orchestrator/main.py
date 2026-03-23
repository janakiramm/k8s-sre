"""
Orchestrator — KubeAuto Day Demo
Watches Kubernetes for pod issues, then coordinates:
  Agent 1 (Diagnose) → Agent 2 (Remediate) → Agent 3 (Verify)

Agents are called via A2A (Agent-to-Agent) protocol over HTTP.
"""

import os
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime

from kubernetes import client, config, watch

from a2a_client import A2AClient, send_message

NAMESPACE = "default"
COOLDOWN_SECONDS = 120
PROBLEM_STATES = {"CrashLoopBackOff", "OOMKilled", "Error"}

DIAGNOSE_URL = os.getenv("DIAGNOSE_URL", "http://localhost:10001")
REMEDIATE_URL = os.getenv("REMEDIATE_URL", "http://localhost:10002")
VERIFY_URL = os.getenv("VERIFY_URL", "http://localhost:10003")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")


# --- Data classes ---

@dataclass
class ProblemEvent:
    pod: str
    namespace: str
    container: str
    reason: str
    state: str
    restart_count: int
    message: str = ""
    deployment: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Diagnosis:
    root_cause: str
    affected_resource: str
    recommended_fix: str
    confidence: str
    raw_output: str = ""


@dataclass
class Remediation:
    action_taken: str
    success: bool
    raw_output: str = ""


@dataclass
class Verification:
    pods_healthy: bool
    details: str
    raw_output: str = ""


# --- Parse structured text from agent responses ---

def _extract_field(text: str, field_name: str, default: str = "") -> str:
    """Extract 'FIELD: value' from agent output text.

    Handles plain text, markdown bold (**FIELD:**), and leading markers (- or *).
    """
    for line in text.splitlines():
        # Strip whitespace, markdown bold markers, and bullet prefixes
        stripped = line.strip().lstrip("-*").strip().replace("**", "")
        prefix = f"{field_name}:"
        if stripped.upper().startswith(prefix.upper()):
            return stripped[len(prefix):].strip()
    return default


# --- A2A agent calls ---

diagnose_client = A2AClient(DIAGNOSE_URL)
remediate_client = A2AClient(REMEDIATE_URL)
verify_client = A2AClient(VERIFY_URL)


def call_agent_diagnose(event: ProblemEvent) -> Diagnosis:
    log.info("[Diagnose] %s/%s — %s (restarts: %d)",
             event.namespace, event.pod, event.reason, event.restart_count)

    problem_report = (
        f"Kubernetes issue detected. Namespace: {event.namespace}. "
        f"Pod: {event.pod}. Container: {event.container}. "
        f"Reason: {event.reason}. State: {event.state}. "
        f"Restart count: {event.restart_count}. "
        f"Deployment: {event.deployment}. "
        f"Message: {event.message}"
    )

    t0 = time.time()
    result = send_message(diagnose_client, problem_report)

    if result.status != "completed":
        log.error("[Diagnose] failed after %.0fs: %s", time.time() - t0, result.error)
        return Diagnosis(
            root_cause="Diagnosis failed",
            affected_resource=f"deployment/{event.deployment}",
            recommended_fix="Manual investigation required",
            confidence="low",
            raw_output=result.error or "",
        )

    output = result.output
    diagnosis = Diagnosis(
        root_cause=_extract_field(output, "ROOT CAUSE", "Unknown"),
        affected_resource=_extract_field(output, "AFFECTED RESOURCE", f"deployment/{event.deployment}"),
        recommended_fix=_extract_field(output, "RECOMMENDED FIX", "Unknown"),
        confidence=_extract_field(output, "CONFIDENCE", "medium").lower(),
        raw_output=output,
    )
    log.info("[Diagnose] done in %.0fs — %s → %s",
             time.time() - t0, diagnosis.root_cause, diagnosis.recommended_fix)
    return diagnosis


def call_agent_remediate(event: ProblemEvent, diagnosis: Diagnosis) -> Remediation:
    log.info("[Remediate] %s — %s", diagnosis.affected_resource, diagnosis.recommended_fix)

    t0 = time.time()
    result = send_message(remediate_client, diagnosis.raw_output)

    if result.status != "completed":
        log.error("[Remediate] failed after %.0fs: %s", time.time() - t0, result.error)
        return Remediation(action_taken="Remediation failed", success=False, raw_output=result.error or "")

    output = result.output
    success_str = _extract_field(output, "SUCCESS", "false").lower()
    remediation = Remediation(
        action_taken=_extract_field(output, "ACTION TAKEN", "Unknown"),
        success=success_str == "true",
        raw_output=output,
    )
    log.info("[Remediate] done in %.0fs — %s (success=%s)",
             time.time() - t0, remediation.action_taken, remediation.success)
    return remediation


def call_agent_verify(event: ProblemEvent, remediation: Remediation) -> Verification:
    log.info("[Verify] %s/%s", event.namespace, event.deployment)

    t0 = time.time()
    result = send_message(verify_client, remediation.raw_output)

    if result.status != "completed":
        log.error("[Verify] failed after %.0fs: %s", time.time() - t0, result.error)
        return Verification(pods_healthy=False, details="Verification failed", raw_output=result.error or "")

    output = result.output
    log.debug("[Verify] raw output:\n%s", output)
    healthy_str = _extract_field(output, "PODS HEALTHY", "false").lower()
    verification = Verification(
        pods_healthy=healthy_str == "true",
        details=_extract_field(output, "DETAILS", _extract_field(output, "VERDICT", "Unknown")),
        raw_output=output,
    )
    log.info("[Verify] done in %.0fs — healthy=%s — %s",
             time.time() - t0, verification.pods_healthy, verification.details)
    return verification


# --- Pipeline ---

def run_pipeline(event: ProblemEvent) -> None:
    log.info("PIPELINE START — %s/%s", event.namespace, event.pod)
    start = time.time()

    diagnosis = call_agent_diagnose(event)
    if diagnosis.confidence == "low":
        log.warning("Low confidence diagnosis — skipping remediation")
        return

    remediation = call_agent_remediate(event, diagnosis)
    if not remediation.success:
        log.error("Remediation failed — skipping verification")
        return

    log.info("Waiting 20s for pods to stabilise...")
    time.sleep(20)
    verification = call_agent_verify(event, remediation)

    elapsed = time.time() - start
    if verification.pods_healthy:
        # Green text for resolved
        log.info("\033[32mPIPELINE RESOLVED in %.1fs — %s → %s → %s\033[0m",
                 elapsed, event.reason, diagnosis.root_cause, remediation.action_taken)
    else:
        # Red text for not resolved
        log.info("\033[31mPIPELINE NOT RESOLVED in %.1fs — %s → %s → %s\033[0m",
                 elapsed, event.reason, diagnosis.root_cause, remediation.action_taken)


# --- Pod problem detection ---

def _check_container_status(cs: client.V1ContainerStatus) -> tuple[str, str, str] | None:
    if cs.state and cs.state.waiting:
        r = cs.state.waiting.reason or ""
        if r in PROBLEM_STATES:
            return r, "waiting", cs.state.waiting.message or ""

    if cs.last_state and cs.last_state.terminated:
        r = cs.last_state.terminated.reason or ""
        if r in PROBLEM_STATES:
            return r, "terminated", ""

    return None


def _get_owner_deployment(pod: client.V1Pod) -> str | None:
    for ref in pod.metadata.owner_references or []:
        if ref.kind == "ReplicaSet":
            parts = ref.name.rsplit("-", 1)
            return parts[0] if len(parts) > 1 else ref.name
    return None


def detect_problem(pod: client.V1Pod) -> ProblemEvent | None:
    if not pod.status or not pod.status.container_statuses:
        return None

    for cs in pod.status.container_statuses:
        result = _check_container_status(cs)
        if result is None:
            continue

        reason, state, message = result
        return ProblemEvent(
            pod=pod.metadata.name,
            namespace=pod.metadata.namespace,
            container=cs.name,
            reason=reason,
            state=state,
            restart_count=cs.restart_count,
            message=message,
            deployment=_get_owner_deployment(pod) or pod.metadata.name,
        )

    return None


# --- Main loop ---

def main() -> None:
    try:
        config.load_incluster_config()
        log.info("Using in-cluster config")
    except config.ConfigException:
        config.load_kube_config()
        log.info("Using kubeconfig")

    v1 = client.CoreV1Api()
    w = watch.Watch()
    cooldowns: dict[str, float] = {}

    # Discover agents
    for name, a2a in [("Diagnose", diagnose_client), ("Remediate", remediate_client), ("Verify", verify_client)]:
        try:
            card = a2a.discover()
            log.info("Agent discovered: %s @ %s", card.name, card.url)
        except Exception as exc:
            log.warning("Agent %s not reachable (%s) — will retry on first call", name, exc)

    log.info("ORCHESTRATOR STARTED — namespace=%s watching=%s cooldown=%ds agents=A2A",
             NAMESPACE, ",".join(sorted(PROBLEM_STATES)), COOLDOWN_SECONDS)

    while True:
        try:
            for event in w.stream(v1.list_namespaced_pod, namespace=NAMESPACE, timeout_seconds=300):
                if event["type"] == "DELETED":
                    continue

                problem = detect_problem(event["object"])
                if problem is None:
                    continue

                last = cooldowns.get(problem.deployment)
                if last and (time.time() - last) < COOLDOWN_SECONDS:
                    continue

                log.warning("PROBLEM DETECTED: %s — %s", problem.pod, problem.reason)
                cooldowns[problem.deployment] = time.time()
                run_pipeline(problem)

        except client.exceptions.ApiException as exc:
            log.error("API error: %s — retrying in 5s", exc.reason)
            time.sleep(5)
        except Exception as exc:
            log.error("Watch error: %s — retrying in 5s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
