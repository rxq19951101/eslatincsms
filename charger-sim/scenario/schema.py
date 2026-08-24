from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Set

from simulator.profiles import OCPP_IDENTITY_RE

from .variables import extract_references


SCHEMA_VERSION = "1.0"
TOP_LEVEL_FIELDS = {"schema_version", "scenario", "environment", "actors", "steps", "reports"}
STEP_FIELDS = {
    "id",
    "actor",
    "action",
    "with",
    "expect",
    "save",
    "timeout",
    "retry",
    "depends_on",
    "parallel",
}
SYSTEM_ACTIONS = {"provision", "await", "assert", "sleep"}
CHARGER_ACTIONS = {
    "connect",
    "disconnect",
    "reconnect",
    "boot",
    "status",
    "authorize",
    "start_transaction",
    "meter_values",
    "stop_transaction",
    "heartbeat",
    "duplicate",
    "send_raw",
    "faulted",
    "meter_before_start",
    "stop_before_start",
    "received_commands",
}
ADMIN_ACTIONS = {
    "login",
    "create_site",
    "register_charger",
    "generate_qr",
    "adjust_wallet",
    "remote_start",
    "remote_stop",
    "ack_alert",
    "resolve_alert",
    "query",
}
APP_ACTIONS = {
    "register",
    "login",
    "check_qr",
    "start_charging",
    "get_active",
    "get_meter_values",
    "stop_charging",
    "settle",
    "get_wallet",
    "get_history",
    "query",
}
PAYMENT_ACTIONS = {"emit_webhook"}
ACTION_BY_ACTOR_TYPE = {
    "charger": CHARGER_ACTIONS,
    "admin": ADMIN_ACTIONS,
    "app": APP_ACTIONS,
    "fake_payment": PAYMENT_ACTIONS,
    "payment": PAYMENT_ACTIONS,
}
ALL_ACTIONS = SYSTEM_ACTIONS | CHARGER_ACTIONS | ADMIN_ACTIONS | APP_ACTIONS | PAYMENT_ACTIONS
SECRET_KEY_RE = re.compile(
    r"(^|_)(password|secret|token|authorization|api_key|card_number|cvv)($|_)", re.IGNORECASE
)
ENV_REFERENCE_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_.-]*\}$")


class ScenarioValidationError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("Scenario validation failed:\n- " + "\n- ".join(errors))


@dataclass(frozen=True)
class ActorSpec:
    name: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepSpec:
    id: str
    actor: str
    action: str
    with_: Dict[str, Any] = field(default_factory=dict)
    expect: Dict[str, Any] = field(default_factory=dict)
    save: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    retry: int = 0
    depends_on: List[str] = field(default_factory=list)
    parallel: Any = False


@dataclass(frozen=True)
class ScenarioDocument:
    schema_version: str
    id: str
    name: str
    description: str
    dependencies: List[str]
    environment: Dict[str, Any]
    actors: Dict[str, ActorSpec]
    steps: List[StepSpec]
    reports: Dict[str, Any]
    source: Optional[str] = None


def _validate_secret_values(value: Any, path: str, errors: List[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if SECRET_KEY_RE.search(str(key)) and item not in (None, ""):
                if not isinstance(item, str) or not ENV_REFERENCE_RE.fullmatch(item):
                    errors.append(f"{item_path} must use a ${{ENV_NAME}} reference; literal secrets are forbidden")
            _validate_secret_values(item, item_path, errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_secret_values(item, f"{path}[{index}]", errors)


def _as_mapping(value: Any, path: str, errors: List[str]) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be a mapping")
        return {}
    return dict(value)


def validate_scenario_data(data: Any, source: Optional[str] = None) -> ScenarioDocument:
    errors: List[str] = []
    if not isinstance(data, Mapping):
        raise ScenarioValidationError(["document must be a mapping"])
    unknown_top = set(data) - TOP_LEVEL_FIELDS
    if unknown_top:
        errors.append(f"unknown top-level fields: {', '.join(sorted(unknown_top))}")
    version = str(data.get("schema_version", ""))
    if version != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    scenario = _as_mapping(data.get("scenario"), "scenario", errors)
    scenario_id = str(scenario.get("id", "")).strip()
    if not scenario_id:
        errors.append("scenario.id is required")
    name = str(scenario.get("name") or scenario_id)
    description = str(scenario.get("description") or "")
    dependencies_raw = scenario.get("dependencies") or []
    dependencies = [str(item) for item in dependencies_raw] if isinstance(dependencies_raw, list) else []
    if dependencies_raw and not isinstance(dependencies_raw, list):
        errors.append("scenario.dependencies must be a list")

    environment = _as_mapping(data.get("environment"), "environment", errors)
    actors_raw = _as_mapping(data.get("actors"), "actors", errors)
    actors: Dict[str, ActorSpec] = {}
    for actor_name, raw in actors_raw.items():
        actor_data = _as_mapping(raw, f"actors.{actor_name}", errors)
        actor_type = str(actor_data.pop("type", "")).strip()
        if actor_type not in ACTION_BY_ACTOR_TYPE:
            errors.append(f"actors.{actor_name}.type is unsupported: {actor_type!r}")
        identity = actor_data.get("ocpp_identity")
        if actor_type == "charger" and identity is not None:
            if not isinstance(identity, str) or (not ENV_REFERENCE_RE.fullmatch(identity) and not OCPP_IDENTITY_RE.fullmatch(identity)):
                errors.append(f"actors.{actor_name}.ocpp_identity is invalid")
        _validate_secret_values(actor_data, f"actors.{actor_name}", errors)
        for reference in sorted(extract_references(actor_data)):
            root = reference.split(".", 1)[0]
            if root not in environment and root != "seed" and not root.isupper():
                errors.append(f"actors.{actor_name} references undefined variable: {reference}")
        actors[str(actor_name)] = ActorSpec(str(actor_name), actor_type, actor_data)

    for reference in sorted(extract_references(environment)):
        root = reference.split(".", 1)[0]
        if root not in environment and root != "seed" and not root.isupper():
            errors.append(f"environment references undefined variable: {reference}")

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        errors.append("steps must be a non-empty list")
        steps_raw = []
    steps: List[StepSpec] = []
    step_ids: Set[str] = set()
    known_variables: Set[str] = set(environment) | {"run_id", "scenario_id", "seed"}
    known_steps: Set[str] = set()
    for index, raw in enumerate(steps_raw):
        path = f"steps[{index}]"
        step_data = _as_mapping(raw, path, errors)
        unknown_fields = set(step_data) - STEP_FIELDS
        if unknown_fields:
            errors.append(f"{path} has unknown fields: {', '.join(sorted(unknown_fields))}")
        step_id = str(step_data.get("id", "")).strip()
        if not step_id:
            errors.append(f"{path}.id is required")
        elif step_id in step_ids:
            errors.append(f"duplicate step id: {step_id}")
        step_ids.add(step_id)
        actor = str(step_data.get("actor", "")).strip()
        action = str(step_data.get("action", "")).strip()
        if action not in ALL_ACTIONS:
            errors.append(f"{path}.action is unknown: {action!r}")
        if action in SYSTEM_ACTIONS:
            if actor not in {"system", ""}:
                errors.append(f"{path}.actor must be system for action {action}")
            actor = "system"
        elif actor not in actors:
            errors.append(f"{path}.actor is undefined: {actor!r}")
        elif action not in ACTION_BY_ACTOR_TYPE.get(actors[actor].type, set()):
            errors.append(f"{path}.action {action!r} is not supported by actor {actor!r}")

        with_data = _as_mapping(step_data.get("with"), f"{path}.with", errors)
        expect = _as_mapping(step_data.get("expect"), f"{path}.expect", errors)
        save_raw = _as_mapping(step_data.get("save"), f"{path}.save", errors)
        save = {str(key): str(value) for key, value in save_raw.items()}
        _validate_secret_values(with_data, f"{path}.with", errors)
        _validate_secret_values(expect, f"{path}.expect", errors)

        references = extract_references(with_data) | extract_references(expect)
        for reference in sorted(references):
            root = reference.split(".", 1)[0]
            if root not in known_variables and not root.isupper():
                errors.append(f"{path} references undefined variable: {reference}")

        depends_raw = step_data.get("depends_on") or []
        if isinstance(depends_raw, str):
            depends_on = [depends_raw]
        elif isinstance(depends_raw, list):
            depends_on = [str(item) for item in depends_raw]
        else:
            errors.append(f"{path}.depends_on must be a string or list")
            depends_on = []
        for dependency in depends_on:
            if dependency not in known_steps:
                errors.append(f"{path}.depends_on references a non-previous step: {dependency}")

        try:
            timeout = float(step_data.get("timeout", 30))
            if timeout <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{path}.timeout must be positive")
            timeout = 30.0
        try:
            retry = int(step_data.get("retry", 0))
            if retry < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{path}.retry must be a non-negative integer")
            retry = 0

        steps.append(
            StepSpec(
                id=step_id,
                actor=actor,
                action=action,
                with_=with_data,
                expect=expect,
                save=save,
                timeout=timeout,
                retry=retry,
                depends_on=depends_on,
                parallel=step_data.get("parallel", False),
            )
        )
        known_steps.add(step_id)
        known_variables.update(save)

    reports = _as_mapping(data.get("reports"), "reports", errors)
    _validate_secret_values(environment, "environment", errors)
    _validate_secret_values(reports, "reports", errors)
    if errors:
        raise ScenarioValidationError(errors)
    return ScenarioDocument(
        schema_version=version,
        id=scenario_id,
        name=name,
        description=description,
        dependencies=dependencies,
        environment=environment,
        actors=actors,
        steps=steps,
        reports=reports,
        source=source,
    )
