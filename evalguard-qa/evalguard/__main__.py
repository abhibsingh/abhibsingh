"""Command-line entry point: python -m evalguard."""
import argparse
import sys
from .core import evaluate, read_json
from .providers import OllamaProvider, ReplayProvider
from .reporting import write_reports


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run AI response regression checks")
    parser.add_argument("--suite", default="datasets/support_assistant.json")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--responses", help="Replay a JSON response fixture without a model")
    source.add_argument("--ollama", action="store_true", help="Evaluate a live Ollama model")
    parser.add_argument("--model", help="Exact model name already installed in Ollama")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--out", default="reports")
    args = parser.parse_args(argv)
    try:
        cases = read_json(args.suite)
        provider = (ReplayProvider(args.responses) if args.responses else
                    OllamaProvider(args.model, args.base_url, args.timeout))
        report = evaluate(cases, provider, args.min_pass_rate)
        write_reports(report, args.out)
    except (ValueError, OSError, TypeError) as exc:
        print(f"Configuration/report error: {exc}", file=sys.stderr)
        return 2
    print(f"{'PASS' if report['gate_passed'] else 'FAIL'} | "
          f"{report['passed']}/{report['total']} cases | "
          f"critical failures: {report['critical_failures']} | reports: {args.out}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
