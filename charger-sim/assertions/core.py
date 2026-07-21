from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping


class AssertionFailure(AssertionError):
    pass


def extract_path(value: Any, path: str) -> Any:
    normalized = path.strip()
    if normalized in {"", "$"}:
        return value
    if normalized.startswith("$."):
        normalized = normalized[2:]
    current = value
    for part in normalized.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise AssertionFailure(f"Path does not exist: {path}")
    return current


OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "matches",
    "exists",
    "in",
    "greater_than",
    "greater_or_equal",
    "less_than",
    "less_or_equal",
    "count",
    "min_count",
    "max_count",
    "unique_by",
    "each",
    "any_match",
    "none_match",
}


def _items(value: Any, path: str) -> Iterable[Any]:
    if not isinstance(value, (list, tuple)):
        raise AssertionFailure(f"{path}: expected a list, got {type(value).__name__}")
    return value


def _matches_mapping(item: Any, conditions: Mapping[str, Any]) -> bool:
    try:
        evaluate_expectations(item, conditions)
    except AssertionFailure:
        return False
    return True


def _assert_value(path: str, actual: Any, expected: Any) -> None:
    if isinstance(expected, Mapping) and set(expected) & OPERATORS:
        if "exists" in expected:
            should_exist = bool(expected["exists"])
            if should_exist != (actual is not None):
                raise AssertionFailure(f"{path}: expected exists={should_exist}, got {actual!r}")
        if "equals" in expected and actual != expected["equals"]:
            raise AssertionFailure(f"{path}: expected {expected['equals']!r}, got {actual!r}")
        if "not_equals" in expected and actual == expected["not_equals"]:
            raise AssertionFailure(f"{path}: expected a value other than {expected['not_equals']!r}")
        if "contains" in expected and expected["contains"] not in actual:
            raise AssertionFailure(f"{path}: expected to contain {expected['contains']!r}, got {actual!r}")
        if "matches" in expected and re.search(str(expected["matches"]), str(actual)) is None:
            raise AssertionFailure(f"{path}: {actual!r} does not match {expected['matches']!r}")
        if "in" in expected and actual not in expected["in"]:
            raise AssertionFailure(f"{path}: expected one of {expected['in']!r}, got {actual!r}")
        comparisons = {
            "greater_than": lambda left, right: left > right,
            "greater_or_equal": lambda left, right: left >= right,
            "less_than": lambda left, right: left < right,
            "less_or_equal": lambda left, right: left <= right,
        }
        for operator, comparison in comparisons.items():
            if operator in expected and not comparison(actual, expected[operator]):
                raise AssertionFailure(f"{path}: {actual!r} failed {operator} {expected[operator]!r}")
        if "count" in expected and len(actual) != int(expected["count"]):
            raise AssertionFailure(f"{path}: expected count={expected['count']}, got {len(actual)}")
        if "min_count" in expected and len(actual) < int(expected["min_count"]):
            raise AssertionFailure(f"{path}: expected min_count={expected['min_count']}, got {len(actual)}")
        if "max_count" in expected and len(actual) > int(expected["max_count"]):
            raise AssertionFailure(f"{path}: expected max_count={expected['max_count']}, got {len(actual)}")
        if "unique_by" in expected:
            items = list(_items(actual, path))
            values = [extract_path(item, str(expected["unique_by"])) for item in items]
            if len(values) != len({repr(value) for value in values}):
                raise AssertionFailure(f"{path}: duplicate values found for {expected['unique_by']!r}")
        if "each" in expected:
            conditions = expected["each"]
            if not isinstance(conditions, Mapping):
                raise AssertionFailure(f"{path}: each must be a mapping")
            for index, item in enumerate(_items(actual, path)):
                try:
                    evaluate_expectations(item, conditions)
                except AssertionFailure as exc:
                    raise AssertionFailure(f"{path}.{index}: {exc}") from exc
        if "any_match" in expected:
            conditions = expected["any_match"]
            if not isinstance(conditions, Mapping) or not any(
                _matches_mapping(item, conditions) for item in _items(actual, path)
            ):
                raise AssertionFailure(f"{path}: no item matched {conditions!r}")
        if "none_match" in expected:
            conditions = expected["none_match"]
            if not isinstance(conditions, Mapping) or any(
                _matches_mapping(item, conditions) for item in _items(actual, path)
            ):
                raise AssertionFailure(f"{path}: an item unexpectedly matched {conditions!r}")
        return
    if actual != expected:
        raise AssertionFailure(f"{path}: expected {expected!r}, got {actual!r}")


def evaluate_expectations(result: Dict[str, Any], expectations: Mapping[str, Any]) -> None:
    for path, expected in expectations.items():
        try:
            actual = extract_path(result, str(path))
        except AssertionFailure:
            if isinstance(expected, Mapping) and expected.get("exists") is False:
                continue
            raise
        _assert_value(str(path), actual, expected)
