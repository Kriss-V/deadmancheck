"""
Assertion evaluation engine.

Each assertion rule: {"field": "rows_exported", "op": ">", "value": 0}
Supported ops: > >= < <= == != exists contains
"""
import json
from typing import Any


SUPPORTED_OPS = {">", ">=", "<", "<=", "==", "!=", "exists", "contains"}


def evaluate_assertions(rules_json: str | None, payload: dict) -> list[dict]:
    """
    Evaluate assertion rules against a ping payload.
    Returns a list of result dicts, each with: field, op, value, actual, passed.
    """
    if not rules_json:
        return []

    try:
        rules = json.loads(rules_json)
    except (json.JSONDecodeError, TypeError):
        return []

    results = []
    for rule in rules:
        field = rule.get("field", "")
        op = rule.get("op", "")
        expected = rule.get("value")

        if not field or op not in SUPPORTED_OPS:
            continue

        actual = _get_nested(payload, field)
        passed = _check(op, actual, expected)

        results.append({
            "field": field,
            "op": op,
            "value": expected,
            "actual": actual,
            "passed": passed,
        })

    return results


def all_passed(results: list[dict]) -> bool:
    return all(r["passed"] for r in results)


def failed_results(results: list[dict]) -> list[dict]:
    return [r for r in results if not r["passed"]]


def _get_nested(payload: dict, field: str) -> Any:
    """Support dot notation: 'stats.rows_exported'"""
    parts = field.split(".")
    val = payload
    for part in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


def _check(op: str, actual: Any, expected: Any) -> bool:
    if op == "exists":
        return actual is not None

    if actual is None:
        return False

    try:
        if op == "contains":
            return str(expected) in str(actual)
        if op == "==":
            return _coerce(actual) == _coerce(expected)
        if op == "!=":
            return _coerce(actual) != _coerce(expected)
        if op == ">":
            return float(actual) > float(expected)
        if op == ">=":
            return float(actual) >= float(expected)
        if op == "<":
            return float(actual) < float(expected)
        if op == "<=":
            return float(actual) <= float(expected)
    except (TypeError, ValueError):
        return False

    return False


def _coerce(val: Any) -> Any:
    """Try numeric coercion, fall back to string."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return str(val)
