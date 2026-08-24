#!/usr/bin/env python3
"""Deterministic project-local orchestration registry and hook guards."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


TERMINAL = {"completed", "failed", "blocked", "cancelled", "shutdown", "interrupted", "errored", "stopped"}
ACTIVE = {"pending_init", "running", "waiting", "awaiting_user_approval"}
POLICY_FILES = ("AGENTS.md", "agent-skills/RUNTIME_POLICY.md", ".codex/hooks.json")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y"}


def default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow": {"change_id": "CHG-20260814-ORCH", "current_stage": "orchestration-infrastructure"},
        "active_agents": [],
        "pending_agents": [],
        "last_monitoring_checkpoint": None,
        "convergence_status": "not-started",
        "qa_status": "not-started",
        "unresolved_blockers": [],
        "allow_main_thread_stop": False,
        "mandatory_agents": [],
        "mandatory_convergence_checks": [],
        "completed_convergence_checks": [],
        "current_stage_gate_status": None,
        "pending_results": [],
        "waiting_user_approval": False,
        "must_continue_workflow": True,
        "self_correction_rounds": 0,
        "no_progress_checkpoints": 0,
        "governance": {
            "current_policy_hash": None,
            "last_policy_reload_at": None,
            "reload_required_for_active_agents": [],
        },
    }


def convergence_conditions(state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, bool]:
    """Compute stop-gate facts from the registry, never from a cached allow flag."""
    mandatory = set(state.get("mandatory_agents", []))
    terminal_roles = {a.get("logical_role") for a in records if a.get("status") in TERMINAL}
    checks = set(state.get("mandatory_convergence_checks", []))
    completed = set(state.get("completed_convergence_checks", []))
    return {
        "mandatory_agents_terminal": mandatory.issubset(terminal_roles),
        "mandatory_convergence_checks_complete": checks.issubset(completed),
        "current_stage_gate_formal": state.get("current_stage_gate_status")
        in {"passed", "failed", "blocked", "not-applicable"},
        "no_active_or_pending_agents": not any(a.get("status") in ACTIVE for a in records),
        "no_pending_agent_results": not state.get("pending_results"),
        "no_waiting_user_approval": not as_bool(state.get("waiting_user_approval")),
        "no_must_continue_workflow_stage": not as_bool(state.get("must_continue_workflow")),
        "governance_reload_clear": not state.get("governance", {}).get("reload_required_for_active_agents"),
    }


def normalize_runtime_state(state: dict[str, Any], agents: dict[str, Any]) -> None:
    """Invalidate stale stop permission left by an interrupted or old session."""
    records = agents.get("agents", [])
    if state.get("allow_main_thread_stop") and not all(convergence_conditions(state, records).values()):
        state["allow_main_thread_stop"] = False
        if state.get("convergence_status") == "converged":
            state["convergence_status"] = "not-converged"


class Store:
    def __init__(self, runtime_dir: str | None = None) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        self.root = Path(runtime_dir or os.environ.get("CODEX_RUNTIME_DIR", self.project_root / ".codex/runtime"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / ".orchestrator.lock"
        self.agents_path = self.root / "agents.json"
        self.state_path = self.root / "orchestrator-state.json"

    def _read(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            self._write(path, default)
            return json.loads(json.dumps(default))
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid runtime state {path}: {exc}") from exc

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def transaction(self):
        store = self

        class Tx:
            def __enter__(self):
                store.lock_path.touch(exist_ok=True)
                self.lock = store.lock_path.open("r+")
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX)
                self.agents = store._read(store.agents_path, {"schema_version": 1, "updated_at": None, "agents": []})
                self.state = store._read(store.state_path, default_state())
                normalize_runtime_state(self.state, self.agents)
                self.store = store
                return self

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.agents["updated_at"] = utc_now()
                    store._write(store.agents_path, self.agents)
                    store._write(store.state_path, self.state)
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
                self.lock.close()
                return False

        return Tx()


def current_policy_hash(store: Store) -> str:
    digest = hashlib.sha256()
    for relative in POLICY_FILES:
        path = store.project_root / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.exists():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def refresh_policy(tx: Any) -> str:
    current = current_policy_hash(tx.store)
    governance = tx.state.setdefault("governance", {})
    previous = governance.get("current_policy_hash")
    if previous and previous != current:
        governance["reload_required_for_active_agents"] = sorted(
            set(governance.get("reload_required_for_active_agents", []))
            | {a["runtime_agent_id"] for a in tx.agents.get("agents", []) if a.get("status") in ACTIVE}
        )
        tx.state["allow_main_thread_stop"] = False
        tx.state["convergence_status"] = "not-converged"
    governance["current_policy_hash"] = current
    governance["last_policy_reload_at"] = utc_now()
    return current


def resolve(tx: Any, role: str, change_id: str | None = None) -> dict[str, Any]:
    candidates = [a for a in tx.agents.get("agents", []) if a.get("logical_role") == role]
    if change_id:
        candidates = [a for a in candidates if a.get("task_change_id") == change_id]
    if not candidates:
        raise RuntimeError(f"agent not found in registry: role={role} change_id={change_id or '*'}")
    return sorted(candidates, key=lambda a: a.get("started_at") or "", reverse=True)[0]


def sync_agents(tx: Any) -> None:
    records = tx.agents.get("agents", [])
    tx.state["active_agents"] = [
        {
            "logical_role": a["logical_role"],
            "runtime_agent_id": a["runtime_agent_id"],
            "thread_id": a.get("thread_id"),
            "status": a.get("status"),
            "task_change_id": a.get("task_change_id"),
        }
        for a in records
        if a.get("status") in ACTIVE
    ]
    tx.state["pending_agents"] = [
        {
            "logical_role": a["logical_role"],
            "runtime_agent_id": a["runtime_agent_id"],
            "thread_id": a.get("thread_id"),
            "status": a.get("status"),
            "task_change_id": a.get("task_change_id"),
        }
        for a in records
        if a.get("status") == "pending_init"
    ]


def register(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        policy = refresh_policy(tx)
        if any(a.get("runtime_agent_id") == args.runtime_agent_id for a in tx.agents.get("agents", [])):
            raise RuntimeError(f"runtime_agent_id already exists in registry: {args.runtime_agent_id}")
        if any(a.get("logical_role") == args.role and a.get("status") in ACTIVE for a in tx.agents.get("agents", [])):
            raise RuntimeError(f"duplicate active logical role: {args.role}")
        record = {
            "logical_role": args.role,
            "runtime_agent_id": args.runtime_agent_id,
            "thread_id": args.thread_id,
            "task_change_id": args.change_id,
            "started_at": utc_now(),
            "last_poll_at": utc_now(),
            "last_convergence_check_at": None,
            "status": "pending_init",
            "terminal_result": None,
            "assigned_scope": args.scope,
            "scope_complete": False,
            "self_check_complete": False,
            "convergence_recorded": False,
            "scope_drift": False,
            "verification_complete": False,
            "governance_policy_hash": policy,
            "governance_reload_acknowledged": True,
            "no_progress_checkpoints": 0,
        }
        tx.agents.setdefault("agents", []).append(record)
        tx.state.setdefault("pending_results", []).append(args.runtime_agent_id)
        tx.state["allow_main_thread_stop"] = False
        tx.state["convergence_status"] = "not-converged"
        tx.state["must_continue_workflow"] = True
        sync_agents(tx)
        return {"event": "AGENT_REGISTERED", "logical_role": args.role, "runtime_agent_id": args.runtime_agent_id}


def poll(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        record = resolve(tx, args.role, args.change_id)
        record["last_poll_at"] = utc_now()
        if args.observed_status:
            if args.observed_status not in ACTIVE | TERMINAL:
                raise RuntimeError(f"invalid observed status: {args.observed_status}")
            record["status"] = args.observed_status
        sync_agents(tx)
        if args.timeout:
            return {
                "event": "POLL_INTERVAL_EXPIRED",
                "runtime_agent_id": record["runtime_agent_id"],
                "logical_role": record["logical_role"],
                "status": record["status"],
                "may_interpret_as_terminal": False,
                "next_action": "monitoring_checkpoint_then_continue_poll",
            }
        return {"event": "AGENT_STATUS", "agent": record}


def monitor(args: argparse.Namespace) -> dict[str, Any]:
    """Return deterministic 10-minute monitoring obligations for active Agents."""
    with Store(args.runtime_dir).transaction() as tx:
        refresh_policy(tx)
        current = dt.datetime.now(dt.timezone.utc)
        due = []
        for record in tx.agents.get("agents", []):
            if record.get("status") not in ACTIVE:
                continue
            checkpoint = record.get("last_checkpoint", {}).get("at") or record.get("started_at")
            try:
                age = (current - dt.datetime.fromisoformat(checkpoint.replace("Z", "+00:00"))).total_seconds() if checkpoint else 10**9
            except (AttributeError, ValueError):
                age = 10**9
            if age >= 600:
                due.append({"logical_role": record["logical_role"], "runtime_agent_id": record["runtime_agent_id"], "age_seconds": int(age), "action": "monitoring_checkpoint"})
        return {"event": "MONITORING_CADENCE_CHECK", "interval_seconds": 600, "due": due, "convergence_check_required": bool(due)}


def checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        record = resolve(tx, args.role, args.change_id)
        progress = json.loads(args.progress_json) if args.progress_json else {}
        meaningful = as_bool(progress.get("meaningful_progress", args.meaningful_progress))
        checkpoint_data = {
            "at": utc_now(),
            "runtime_status": record.get("status"),
            "current_task": progress.get("current_task", record.get("assigned_scope")),
            "meaningful_progress": meaningful,
            "files_changed": progress.get("files_changed", []),
            "scope_drift": as_bool(progress.get("scope_drift", False)),
            "repeated_analysis": as_bool(progress.get("repeated_analysis", False)),
            "blocker": progress.get("blocker"),
            "convergence_state": tx.state.get("convergence_status"),
            "expected_next_action": progress.get("expected_next_action"),
        }
        record["last_poll_at"] = utc_now()
        record["last_convergence_check_at"] = utc_now()
        record["last_checkpoint"] = checkpoint_data
        tx.state["last_monitoring_checkpoint"] = checkpoint_data
        if meaningful:
            record["no_progress_checkpoints"] = 0
            tx.state["no_progress_checkpoints"] = 0
        else:
            record["no_progress_checkpoints"] = record.get("no_progress_checkpoints", 0) + 1
            tx.state["no_progress_checkpoints"] = tx.state.get("no_progress_checkpoints", 0) + 1
            if record["no_progress_checkpoints"] >= 2:
                if tx.state.get("self_correction_rounds", 0) < 2:
                    tx.state["self_correction_rounds"] = tx.state.get("self_correction_rounds", 0) + 1
                    tx.state["convergence_status"] = "self-correction-required"
                    record["self_correction_required"] = True
                else:
                    tx.state["convergence_status"] = "blocked-no-progress"
                    tx.state.setdefault("unresolved_blockers", []).append("no meaningful progress after two self-correction cycles")
        sync_agents(tx)
        return {"event": "MONITORING_CHECKPOINT", "checkpoint": checkpoint_data, "state": tx.state}


def convergence(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        refresh_policy(tx)
        records = tx.agents.get("agents", [])
        conditions = convergence_conditions(tx.state, records)
        allowed = all(conditions.values())
        tx.state["convergence_status"] = "converged" if allowed else "not-converged"
        tx.state["allow_main_thread_stop"] = allowed
        for record in records:
            record["last_convergence_check_at"] = utc_now()
            record["convergence_recorded"] = True
        sync_agents(tx)
        return {"event": "CONVERGENCE_CHECK", "allow_main_thread_stop": allowed, "conditions": conditions}


def record_terminal(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        if args.status not in TERMINAL:
            raise RuntimeError("record-terminal requires a terminal status")
        record = resolve(tx, args.role, args.change_id)
        terminal_result = json.loads(args.result_json) if args.result_json else {"status": args.status}
        if args.blocked_reason:
            terminal_result["blocked_reason"] = args.blocked_reason
        record.update({
            "status": args.status,
            "terminal_result": terminal_result,
            "scope_complete": as_bool(args.scope_complete),
            "self_check_complete": as_bool(args.self_check_complete),
            "convergence_recorded": as_bool(args.convergence_recorded),
            "scope_drift": as_bool(args.scope_drift),
            "verification_complete": as_bool(args.verification_complete),
            "last_poll_at": utc_now(),
            "last_convergence_check_at": utc_now(),
        })
        tx.state["allow_main_thread_stop"] = False
        tx.state["convergence_status"] = "not-converged"
        pending = tx.state.setdefault("pending_results", [])
        if record["runtime_agent_id"] in pending:
            pending.remove(record["runtime_agent_id"])
        sync_agents(tx)
        return {"event": "AGENT_TERMINAL_RESULT_RECORDED", "agent": record}


def stop_hook(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        refresh_policy(tx)
        sync_agents(tx)
        conditions = convergence_conditions(tx.state, tx.agents.get("agents", []))
        allowed = all(conditions.values())
        tx.state["allow_main_thread_stop"] = allowed
        tx.state["convergence_status"] = "converged" if allowed else "not-converged"
        if allowed:
            return {"decision": "allow", "event": "MAIN_STOP_ALLOWED"}
        return {
            "decision": "block",
            "event": "MAIN_STOP_BLOCKED",
            "reason": "orchestrator convergence gate is not satisfied",
            "conditions": conditions,
            "prompt": "检查 active Agent、接收 terminal result、执行 convergence check，并继续 workflow；POLL_INTERVAL_EXPIRED 不是终态。",
        }


def subagent_stop_hook(args: argparse.Namespace) -> dict[str, Any]:
    payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    runtime_id = payload.get("runtime_agent_id") or payload.get("agent_id") or payload.get("agent", {}).get("runtime_agent_id")
    thread_id = payload.get("thread_id") or payload.get("agent", {}).get("thread_id")
    with Store(args.runtime_dir).transaction() as tx:
        record = next((a for a in tx.agents.get("agents", []) if a.get("runtime_agent_id") == runtime_id), None)
        if record is None and thread_id:
            record = next((a for a in tx.agents.get("agents", []) if a.get("thread_id") == thread_id), None)
            runtime_id = record.get("runtime_agent_id") if record else runtime_id
        if record is None:
            return {"decision": "block", "event": "SUBAGENT_STOP_BLOCKED", "reason": "runtime_agent_id is not in agents.json", "prompt": "先从 Registry 注册或恢复 Agent。"}
        scope_exit_valid = as_bool(record.get("scope_complete")) or (
            record.get("status") in {"blocked", "failed", "errored"}
            and bool(record.get("terminal_result", {}).get("blocked_reason") or record.get("terminal_result", {}).get("reason"))
        )
        missing = [key for key, valid in {
            "assigned_scope_completed_or_explicitly_blocked": scope_exit_valid,
            "self_check_complete": as_bool(record.get("self_check_complete")),
            "convergence_recorded": as_bool(record.get("convergence_recorded")),
            "verification_complete": as_bool(record.get("verification_complete")),
        }.items() if not valid]
        if record.get("scope_drift"):
            missing.append("scope_drift=false")
        if record.get("status") not in TERMINAL:
            missing.append("terminal_status")
        if runtime_id in tx.state.get("governance", {}).get("reload_required_for_active_agents", []):
            missing.append("governance_reload_acknowledged")
        if missing:
            return {
                "decision": "block",
                "event": "SUBAGENT_STOP_BLOCKED",
                "runtime_agent_id": runtime_id,
                "missing": missing,
                "reason": "mandatory SubagentStop validation is incomplete",
                "prompt": "执行 focused correction pass，补齐 scope/self-check/convergence/verification/治理 reload 后再停止。",
            }
        return {"decision": "allow", "event": "SUBAGENT_STOP_ALLOWED", "runtime_agent_id": runtime_id}


def acknowledge_reload(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        record = resolve(tx, args.role, args.change_id)
        policy = refresh_policy(tx)
        record["governance_policy_hash"] = policy
        record["governance_reload_acknowledged"] = True
        pending = tx.state.setdefault("governance", {}).setdefault("reload_required_for_active_agents", [])
        if record["runtime_agent_id"] in pending:
            pending.remove(record["runtime_agent_id"])
        return {"event": "GOVERNANCE_RELOAD_ACKNOWLEDGED", "runtime_agent_id": record["runtime_agent_id"], "policy_hash": policy}


def workflow_update(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        workflow = tx.state.setdefault("workflow", {})
        if args.workflow_id:
            workflow["change_id"] = args.workflow_id
        workflow["current_stage"] = args.stage
        tx.state["current_stage_gate_status"] = args.gate_status
        tx.state["must_continue_workflow"] = as_bool(args.must_continue)
        tx.state["allow_main_thread_stop"] = False
        tx.state["convergence_status"] = "not-converged"
        if args.qa_status:
            tx.state["qa_status"] = args.qa_status
        if args.mandatory_checks:
            tx.state["mandatory_convergence_checks"] = json.loads(args.mandatory_checks)
        if args.completed_checks:
            tx.state["completed_convergence_checks"] = json.loads(args.completed_checks)
        if args.mandatory_agents:
            tx.state["mandatory_agents"] = json.loads(args.mandatory_agents)
        if args.waiting_user_approval is not None:
            tx.state["waiting_user_approval"] = as_bool(args.waiting_user_approval)
            if as_bool(args.waiting_user_approval):
                tx.state["allow_main_thread_stop"] = False
                tx.state["must_continue_workflow"] = True
                tx.state["convergence_status"] = "awaiting-user-approval"
        return {"event": "WORKFLOW_STATE_UPDATED", "workflow": tx.state["workflow"], "gate_status": args.gate_status}


def recover(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        records = [
            {"logical_role": a["logical_role"], "runtime_agent_id": a["runtime_agent_id"], "thread_id": a.get("thread_id"), "action": "resume-existing-agent"}
            for a in tx.agents.get("agents", []) if a.get("status") in ACTIVE
        ]
        sync_agents(tx)
        return {"event": "RECOVERY_PLAN", "duplicate_agent_creation": False, "agents": records}


def resume_existing(args: argparse.Namespace) -> dict[str, Any]:
    with Store(args.runtime_dir).transaction() as tx:
        refresh_policy(tx)
        record = resolve(tx, args.role, args.change_id)
        if record.get("status") in TERMINAL:
            record.update({
                "status": "pending_init",
                "terminal_result": None,
                "scope_complete": False,
                "self_check_complete": False,
                "convergence_recorded": False,
                "verification_complete": False,
                "scope_drift": False,
                "self_correction_required": False,
                "last_poll_at": utc_now(),
                "last_convergence_check_at": None,
                "last_checkpoint": None,
                "resumed_at": utc_now(),
            })
            pending = tx.state.setdefault("pending_results", [])
            if record["runtime_agent_id"] not in pending:
                pending.append(record["runtime_agent_id"])
            tx.state["allow_main_thread_stop"] = False
            tx.state["convergence_status"] = "not-converged"
            tx.state["must_continue_workflow"] = True
            sync_agents(tx)
            return {
                "event": "AGENT_REACTIVATED",
                "logical_role": record["logical_role"],
                "runtime_agent_id": record["runtime_agent_id"],
                "thread_id": record.get("thread_id"),
                "status": record.get("status"),
                "duplicate_agent_creation": False,
            }
        return {
            "event": "RESUME_EXISTING_AGENT",
            "logical_role": record["logical_role"],
            "runtime_agent_id": record["runtime_agent_id"],
            "thread_id": record.get("thread_id"),
            "status": record.get("status"),
            "duplicate_agent_creation": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    register_parser = sub.add_parser("register-agent")
    register_parser.add_argument("--role", required=True)
    register_parser.add_argument("--runtime-agent-id", required=True)
    register_parser.add_argument("--thread-id")
    register_parser.add_argument("--change-id", required=True)
    register_parser.add_argument("--scope", required=True)
    register_parser.set_defaults(func=register)

    poll_parser = sub.add_parser("poll")
    poll_parser.add_argument("--role", required=True)
    poll_parser.add_argument("--change-id")
    poll_parser.add_argument("--observed-status")
    poll_parser.add_argument("--timeout", action="store_true")
    poll_parser.set_defaults(func=poll)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--role", required=True)
    status_parser.add_argument("--change-id")
    status_parser.set_defaults(observed_status=None, timeout=False)
    status_parser.set_defaults(func=poll)

    resume_parser = sub.add_parser("resume")
    resume_parser.add_argument("--role", required=True)
    resume_parser.add_argument("--change-id")
    resume_parser.set_defaults(func=resume_existing)

    checkpoint_parser = sub.add_parser("checkpoint")
    checkpoint_parser.add_argument("--role", required=True)
    checkpoint_parser.add_argument("--change-id")
    checkpoint_parser.add_argument("--meaningful-progress", default="false")
    checkpoint_parser.add_argument("--progress-json")
    checkpoint_parser.set_defaults(func=checkpoint)

    convergence_parser = sub.add_parser("convergence-check")
    convergence_parser.set_defaults(func=convergence)

    terminal_parser = sub.add_parser("record-terminal")
    terminal_parser.add_argument("--role", required=True)
    terminal_parser.add_argument("--change-id")
    terminal_parser.add_argument("--status", required=True)
    terminal_parser.add_argument("--result-json")
    terminal_parser.add_argument("--blocked-reason")
    for option in ("scope-complete", "self-check-complete", "convergence-recorded", "verification-complete", "scope-drift"):
        terminal_parser.add_argument(f"--{option}", default="false")
    terminal_parser.set_defaults(func=record_terminal)

    stop_parser = sub.add_parser("stop-hook")
    stop_parser.set_defaults(func=stop_hook)
    subagent_stop_parser = sub.add_parser("subagent-stop-hook")
    subagent_stop_parser.set_defaults(func=subagent_stop_hook)

    reload_parser = sub.add_parser("ack-governance-reload")
    reload_parser.add_argument("--role", required=True)
    reload_parser.add_argument("--change-id")
    reload_parser.set_defaults(func=acknowledge_reload)

    monitor_parser = sub.add_parser("monitor")
    monitor_parser.set_defaults(func=monitor)

    workflow_parser = sub.add_parser("workflow-update")
    workflow_parser.add_argument("--workflow-id")
    workflow_parser.add_argument("--stage", required=True)
    workflow_parser.add_argument("--gate-status", required=True)
    workflow_parser.add_argument("--must-continue", default="false")
    workflow_parser.add_argument("--qa-status")
    workflow_parser.add_argument("--mandatory-checks")
    workflow_parser.add_argument("--completed-checks")
    workflow_parser.add_argument("--mandatory-agents")
    workflow_parser.add_argument("--waiting-user-approval")
    workflow_parser.set_defaults(func=workflow_update)

    recovery_parser = sub.add_parser("recover")
    recovery_parser.set_defaults(func=recover)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = args.func(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"decision": "block", "event": "ORCHESTRATOR_ERROR", "reason": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
