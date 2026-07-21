from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import yaml

from .schema import ScenarioDocument, ScenarioValidationError, validate_scenario_data


def load_scenario(path: Path) -> ScenarioDocument:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioValidationError([f"invalid YAML: {exc}"]) from exc
    return validate_scenario_data(data, source=str(path))


def discover_scenarios(paths: Iterable[Path]) -> List[Path]:
    discovered = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}:
            discovered.append(path)
        elif path.is_dir():
            discovered.extend(path.rglob("*.yml"))
            discovered.extend(path.rglob("*.yaml"))
    return sorted(set(item.resolve() for item in discovered))
