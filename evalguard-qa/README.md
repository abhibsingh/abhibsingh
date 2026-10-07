# EvalGuard QA

**AI response evaluation with repeatable QA checks and CI quality gates.**

[![EvalGuard QA](https://github.com/abhibsingh/abhibsingh/actions/workflows/evalguard-qa.yml/badge.svg)](https://github.com/abhibsingh/abhibsingh/actions/workflows/evalguard-qa.yml)

A Python toolkit for catching regressions in AI assistants: incorrect policy answers, invalid JSON, instruction-following failures, canary disclosure, and latency-budget breaches. Run it offline against recorded responses or against a local Ollama model.

**Status: MVP.** Included responses and latencies are synthetic fixtures, not model benchmark results. Live Ollama behavior must be evaluated on your own machine.

## Why this project

A fluent model answer can still violate an application contract. EvalGuard separates model output from deterministic checks and turns failures into evidence in HTML, JSON, and JUnit XML. The example application is a fictional support assistant with a 30-day refund policy. All examples use synthetic data.

## Quick start — no API key or dependencies

Requires Python 3.11 or newer:

```bash
git clone https://github.com/abhibsingh/abhibsingh.git
cd abhibsingh/evalguard-qa
python -m unittest discover -s tests -v
python -m evalguard --responses examples/responses.good.json --out reports/baseline
```

Expected: `PASS | 8/8 cases`. Open `reports/baseline/report.html` in your browser.

Prove the gate catches failures:

```bash
python -m evalguard --responses examples/responses.regression.json --out reports/regression
```

Expected: `FAIL | 3/8 cases`, one critical failure, and exit code **1**. This is intentional: the fixture contains five regressions. CI verifies this failure path as well as the passing baseline.

## Evaluate an actual local model

Start your Ollama server and ensure a model is installed. Substitute its exact name:

```bash
python -m evalguard --ollama --model YOUR_INSTALLED_MODEL --out reports/live
```

The adapter calls `/api/chat` with system/user messages, `stream: false`, and temperature 0, measuring end-to-end request latency. The default address is `http://localhost:11434`. Use `--base-url` to change it and `--timeout` to set the per-case timeout in seconds. Temperature 0 does not guarantee identical output across runtimes or model versions.

Reference: [Ollama chat API](https://docs.ollama.com/api/chat).

The default CI workflow uses no live model. It verifies evaluator and gate behavior without downloads, credentials, or API costs. The Ollama adapter is covered by mocked request-contract and timeout tests; these are not a substitute for a live model run.

## Evaluation coverage

| Scenario | Assertion | Critical |
| --- | --- | --- |
| Refund policy | Required policy phrase; forbidden incorrect windows | No |
| Unknown fact | Exact abstention response | No |
| Ticket routing | JSON field values and types | No |
| Direct prompt injection | No canary disclosure; expected refusal | Yes |
| Injection in quoted content | No canary disclosure; expected task completion | Yes |
| Output format | Exact integer text | No |
| Response time | Expected content and 10-second latency budget | No |
| JSON type contract | Numeric field remains numeric | No |

A case passes only if every assertion passes. The default overall threshold is 100%. `--min-pass-rate 0.9` allows some noncritical failures, but **any critical failure or provider error still fails the gate**. Missing fixtures, empty responses, and timeouts fail rather than being skipped.

| Exit code | Meaning |
| --- | --- |
| 0 | Quality gate passed |
| 1 | Evaluation or provider failure |
| 2 | Invalid configuration, input, or report-writing error |

## Add cases

Edit `datasets/support_assistant.json` or use `--suite path/to/suite.json`. Put cases in a JSON array:

```json
[{
  "id": "refund-window",
  "category": "policy",
  "critical": false,
  "messages": [
    {"role": "system", "content": "The refund window is 30 days."},
    {"role": "user", "content": "Reply with the refund window only."}
  ],
  "checks": [{"type": "exact", "value": "30 days"}]
}]
```

For replay, supply a JSON object keyed by case ID:

```json
{"refund-window": {"text": "30 days", "latency_ms": 120}}
```

Supported checks:

| Check | Configuration | Behavior |
| --- | --- | --- |
| `exact` | `value` | Trimmed, case-sensitive equality |
| `contains_all` | `values` | All case-insensitive substrings required |
| `forbids` | `values` | No listed case-insensitive substring allowed |
| `json_fields` | `fields` | Strict JSON; required top-level field values and types |
| `latency_ms` | `max` | Maximum response latency in milliseconds |

`json_fields` allows additional fields and is not a full JSON Schema validator.

## Reports and automation

Each run writes `report.html` (readable assertions and expandable responses), `report.json` (machine-readable results), and `junit.xml` (CI test cases and failures). HTML output escapes model-generated text. Reports contain response text: review live reports before sharing. Generated reports are excluded by `.gitignore`.

The [GitHub Actions workflow](../.github/workflows/evalguard-qa.yml) runs automated tests and both fixtures on Python 3.11, 3.12, and 3.13, then uploads reports. This MVP is hosted in a folder in the profile repository, so the workflow is at the repository root.

## Structure

| Path | Purpose |
| --- | --- |
| `evalguard/__main__.py` | CLI and exit codes |
| `evalguard/core.py` | Validation, assertions, and quality gates |
| `evalguard/providers.py` | Replay and Ollama adapter |
| `evalguard/reporting.py` | HTML, JSON, and JUnit reports |
| `datasets/` | Synthetic evaluation scenarios |
| `examples/` | Passing and intentionally failing responses |
| `tests/` | Evaluator, provider, report, and CLI tests |

## Evaluation limits

These are deterministic regression checks, not a general measure of intelligence, factuality, or security. Required phrases can appear in an otherwise incorrect answer. Exact refusals can reject valid paraphrases. Canary checks catch literal disclosure, not encoded or indirect leakage. The suite does not test tool execution, agent side effects, or multi-turn attacks. Latency includes request overhead and may include model loading.

Use representative versioned datasets, repeat live runs, and manually review failures before drawing conclusions about a model. Eight synthetic cases cannot establish production readiness.

## Next improvements

- Compare case outcomes between prompt and model versions.
- Add repeated-run statistics and model/runtime metadata.
- Extend structured-output validation and task-specific datasets.
- Add human-reviewed rubrics for tasks requiring semantic judgment.
