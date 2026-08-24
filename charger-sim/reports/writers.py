from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

from .redaction import redact


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def write_json_report(data: Dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(redact(data), ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def write_junit_report(data: Dict[str, Any], path: Path) -> None:
    steps: List[Dict[str, Any]] = data.get("steps", [])
    failures = sum(1 for step in steps if step.get("outcome") == "FAIL")
    skipped = sum(1 for step in steps if step.get("outcome") in {"BLOCKED", "NOT_RUN"})
    suite = ET.Element(
        "testsuite",
        {
            "name": str(data.get("scenario_id")),
            "tests": str(len(steps)),
            "failures": str(failures),
            "skipped": str(skipped),
            "id": str(data.get("run_id")),
        },
    )
    for step in steps:
        case = ET.SubElement(
            suite,
            "testcase",
            {"name": str(step.get("step_id")), "time": str(step.get("duration_seconds", 0))},
        )
        if step.get("outcome") == "FAIL":
            failure = ET.SubElement(case, "failure", {"message": str(redact(step.get("error", "failed")))})
            failure.text = json.dumps(redact(step.get("result")), default=_json_default)
        elif step.get("outcome") in {"BLOCKED", "NOT_RUN"}:
            ET.SubElement(case, "skipped", {"message": str(step.get("error") or step.get("outcome"))})
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def write_timeline(data: Dict[str, Any], path: Path) -> None:
    lines = [
        f"run_id={data.get('run_id')} scenario={data.get('scenario_id')} outcome={data.get('outcome')}",
        "",
    ]
    for step in data.get("steps", []):
        lines.append(
            f"{step.get('start')} -> {step.get('end')} [{step.get('outcome')}] "
            f"{step.get('step_id')} actor={step.get('actor')} action={step.get('action')} "
            f"trace_id={step.get('trace_id') or '-'}"
        )
        if step.get("error"):
            lines.append(f"  error: {redact(str(step['error']))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_all_reports(data: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    run_dir = output_dir / str(data["scenario_id"])
    run_dir.mkdir(parents=True, exist_ok=True)
    stem = str(data["run_id"])
    paths = {
        "json": run_dir / f"{stem}.json",
        "junit": run_dir / f"{stem}.junit.xml",
        "timeline": run_dir / f"{stem}.timeline.txt",
    }
    write_json_report(data, paths["json"])
    write_junit_report(data, paths["junit"])
    write_timeline(data, paths["timeline"])
    return {name: str(path) for name, path in paths.items()}
