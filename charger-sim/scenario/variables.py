from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Set


VARIABLE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.-]*)\}")


class VariableResolutionError(ValueError):
    pass


def extract_references(value: Any) -> Set[str]:
    references: Set[str] = set()
    if isinstance(value, str):
        references.update(VARIABLE_RE.findall(value))
    elif isinstance(value, Mapping):
        for item in value.values():
            references.update(extract_references(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            references.update(extract_references(item))
    return references


def lookup_variable(name: str, values: Mapping[str, Any]) -> Any:
    current: Any = values
    for part in name.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            raise VariableResolutionError(f"Undefined variable: {name}")
    return current


def resolve_value(value: Any, values: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        full = VARIABLE_RE.fullmatch(value)
        if full:
            return lookup_variable(full.group(1), values)

        def replace(match: re.Match) -> str:
            return str(lookup_variable(match.group(1), values))

        return VARIABLE_RE.sub(replace, value)
    if isinstance(value, list):
        return [resolve_value(item, values) for item in value]
    if isinstance(value, tuple):
        return tuple(resolve_value(item, values) for item in value)
    if isinstance(value, Mapping):
        return {key: resolve_value(item, values) for key, item in value.items()}
    return value


def build_environment(
    declared: Mapping[str, Any],
    process_environment: Mapping[str, str],
    initial: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    values: Dict[str, Any] = dict(process_environment)
    if initial:
        values.update(initial)
    pending = dict(declared)
    while pending:
        progressed = False
        for key, raw in list(pending.items()):
            try:
                values[key] = resolve_value(raw, values)
            except VariableResolutionError:
                continue
            del pending[key]
            progressed = True
        if not progressed:
            unresolved = ", ".join(sorted(pending))
            raise VariableResolutionError(f"Unable to resolve environment variables: {unresolved}")
    return values


def flatten_saved_names(save: Mapping[str, Any]) -> Iterable[str]:
    return save.keys()
