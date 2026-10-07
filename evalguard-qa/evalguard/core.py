"""Dataset validation, deterministic checks, and evaluation orchestration."""
import json
import math
from pathlib import Path


class ConfigurationError(ValueError):
    """Invalid suite or response fixture."""


def read_json(path):
    def invalid(value):
        raise ConfigurationError(f"Non-finite JSON number: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def validate_cases(cases):
    if not isinstance(cases, list) or not cases:
        raise ConfigurationError("Suite must be a non-empty list")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ConfigurationError("Every case must be an object")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ConfigurationError("Case IDs must be non-empty, unique strings")
        seen.add(identifier)
        if not isinstance(case.get("critical", False), bool):
            raise ConfigurationError(f"{identifier}: critical must be boolean")
        messages = case.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ConfigurationError(f"{identifier}: messages required")
        for message in messages:
            if (not isinstance(message, dict)
                    or message.get("role") not in {"system", "user", "assistant"}
                    or not isinstance(message.get("content"), str)):
                raise ConfigurationError(f"{identifier}: invalid message")
        checks = case.get("checks")
        if not isinstance(checks, list) or not checks:
            raise ConfigurationError(f"{identifier}: checks required")
        for check in checks:
            if not isinstance(check, dict):
                raise ConfigurationError("Check must be an object")
            kind = check.get("type")
            if kind == "exact":
                valid = isinstance(check.get("value"), str)
            elif kind in {"contains_all", "forbids"}:
                values = check.get("values")
                valid = (isinstance(values, list) and bool(values)
                         and all(isinstance(v, str) and bool(v) for v in values))
            elif kind == "json_fields":
                fields = check.get("fields")
                valid = isinstance(fields, dict) and bool(fields)
            elif kind == "latency_ms":
                limit = check.get("max")
                valid = (type(limit) in {int, float} and math.isfinite(limit) and limit > 0)
            else:
                raise ConfigurationError(f"Unknown check type: {kind}")
            if not valid:
                raise ConfigurationError(f"{identifier}: invalid {kind} check")
    return cases


def check_response(check, text, latency_ms):
    kind = check["type"]
    folded = text.casefold()
    if kind == "exact":
        passed = text.strip() == check["value"]
        detail = "Trimmed response must equal the expected text (case-sensitive)."
    elif kind == "contains_all":
        missing = [v for v in check["values"] if v.casefold() not in folded]
        passed = not missing
        detail = "Missing required text: " + ", ".join(missing) if missing else "All required text found."
    elif kind == "forbids":
        found = [v for v in check["values"] if v.casefold() in folded]
        passed = not found
        detail = "Forbidden text found: " + ", ".join(found) if found else "No forbidden text found."
    elif kind == "json_fields":
        try:
            def invalid(value):
                raise ValueError(value)
            parsed = json.loads(text, parse_constant=invalid)
            passed = isinstance(parsed, dict) and all(
                key in parsed and type(parsed[key]) is type(value) and parsed[key] == value
                for key, value in check["fields"].items()
            )
            detail = "Required top-level JSON fields must match their expected values and types."
        except (ValueError, TypeError):
            passed, detail = False, "Response is not strict JSON."
    elif kind == "latency_ms":
        passed = latency_ms <= check["max"]
        detail = f"Observed {latency_ms:.1f} ms; budget {check['max']} ms."
    else:
        raise ConfigurationError(f"Unknown check type: {kind}")
    return {"type": kind, "passed": passed, "detail": detail}


def evaluate(cases, provider, min_pass_rate=1.0):
    validate_cases(cases)
    if not math.isfinite(min_pass_rate) or not 0 <= min_pass_rate <= 1:
        raise ConfigurationError("Minimum pass rate must be between 0 and 1")
    results = []
    for case in cases:
        try:
            text, latency_ms = provider.generate(case)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty or non-string response")
            if (type(latency_ms) not in {int, float}
                    or not math.isfinite(latency_ms) or latency_ms < 0):
                raise ValueError("Invalid response latency")
            checks = [check_response(c, text, latency_ms) for c in case["checks"]]
            error = None
        except Exception as exc:
            # Provider errors are evaluation failures, never silent skips.
            text, latency_ms, checks = "", 0, []
            error = f"{type(exc).__name__}: {exc}"
        results.append({
            "id": case["id"], "category": case.get("category", "general"),
            "critical": case.get("critical", False), "response": text,
            "latency_ms": latency_ms, "checks": checks, "error": error,
            "passed": error is None and all(c["passed"] for c in checks),
        })
    passed = sum(r["passed"] for r in results)
    critical_failures = sum(r["critical"] and not r["passed"] for r in results)
    errors = sum(r["error"] is not None for r in results)
    rate = passed / len(results)
    return {
        "provider": provider.name, "total": len(results), "passed": passed,
        "failed": len(results) - passed, "pass_rate": rate,
        "critical_failures": critical_failures, "provider_errors": errors,
        "min_pass_rate": min_pass_rate,
        "gate_passed": rate >= min_pass_rate and not critical_failures and not errors,
        "results": results,
    }
