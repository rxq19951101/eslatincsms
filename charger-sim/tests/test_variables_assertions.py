from __future__ import annotations

import unittest

from assertions import AssertionFailure, evaluate_expectations, extract_path
from scenario.variables import VariableResolutionError, build_environment, resolve_value


class VariableTests(unittest.TestCase):
    def test_nested_variables_preserve_full_value_type(self) -> None:
        values = {"count": 3, "actor": {"token": "hidden"}}
        self.assertEqual(resolve_value("${count}", values), 3)
        self.assertEqual(resolve_value("Bearer ${actor.token}", values), "Bearer hidden")

    def test_environment_requires_missing_process_variable(self) -> None:
        with self.assertRaises(VariableResolutionError):
            build_environment({"password": "${MISSING_PASSWORD}"}, {})


class AssertionTests(unittest.TestCase):
    def test_expectation_operators_and_paths(self) -> None:
        result = {"status": 200, "body": {"items": ["a", "b"], "id": "abc-123"}}
        evaluate_expectations(
            result,
            {
                "status": {"in": [200, 201]},
                "body.items": {"contains": "b"},
                "body.id": {"matches": r"^abc"},
            },
        )
        self.assertEqual(extract_path(result, "$.body.items.0"), "a")

    def test_failed_expectation_raises(self) -> None:
        with self.assertRaises(AssertionFailure):
            evaluate_expectations({"status": 500}, {"status": 200})

    def test_collection_invariants_cover_count_uniqueness_and_matching(self) -> None:
        items = [
            {"id": "a", "status": "completed", "amount": 10},
            {"id": "b", "status": "completed", "amount": 20},
        ]
        evaluate_expectations(
            {"body": items},
            {
                "body": {
                    "count": 2,
                    "unique_by": "id",
                    "each": {"status": "completed", "amount": {"greater_than": 0}},
                    "any_match": {"id": "b"},
                    "none_match": {"status": "orphaned"},
                }
            },
        )

    def test_duplicate_invariant_fails(self) -> None:
        with self.assertRaisesRegex(AssertionFailure, "duplicate values"):
            evaluate_expectations(
                {"body": [{"event_id": "same"}, {"event_id": "same"}]},
                {"body": {"unique_by": "event_id"}},
            )


if __name__ == "__main__":
    unittest.main()
