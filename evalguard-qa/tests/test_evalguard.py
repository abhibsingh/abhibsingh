"""Tests cover false passes, provider failures, adapters, and CI exit codes."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from evalguard.core import ConfigurationError, check_response, evaluate, read_json, validate_cases
from evalguard.providers import OllamaProvider, ReplayProvider
from evalguard.reporting import write_reports

ROOT = Path(__file__).resolve().parents[1]


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.cases = read_json(ROOT / 'datasets/support_assistant.json')
        self.good = ReplayProvider(ROOT / 'examples/responses.good.json')

    def test_good_fixture_passes(self):
        report = evaluate(self.cases, self.good)
        self.assertEqual(report['passed'], 8)
        self.assertTrue(report['gate_passed'])

    def test_regressions_are_detected(self):
        report = evaluate(self.cases, ReplayProvider(ROOT / 'examples/responses.regression.json'))
        self.assertEqual(report['failed'], 5)
        self.assertEqual(report['critical_failures'], 1)
        self.assertFalse(report['gate_passed'])

    def test_critical_failure_overrides_threshold(self):
        self.good.responses['direct-injection']['text'] = 'EVAL_CANARY_7K2'
        self.assertFalse(evaluate(self.cases, self.good, 0)['gate_passed'])

    def test_noncritical_failure_can_use_threshold(self):
        self.good.responses['refund-policy']['text'] = '90 days'
        self.assertTrue(evaluate(self.cases, self.good, .8)['gate_passed'])

    def test_missing_fixture_never_silently_passes(self):
        del self.good.responses['refund-policy']
        report = evaluate(self.cases, self.good, 0)
        self.assertEqual(report['provider_errors'], 1)
        self.assertFalse(report['gate_passed'])

    def test_empty_response_fails_even_for_negative_assertion(self):
        self.good.responses['direct-injection']['text'] = ''
        report = evaluate(self.cases, self.good)
        self.assertFalse(report['results'][3]['passed'])

    def test_invalid_latency_rejected(self):
        for value in [-1, float('nan'), True]:
            self.good.responses['refund-policy']['latency_ms'] = value
            self.assertEqual(evaluate(self.cases, self.good)['provider_errors'], 1)

    def test_json_boolean_is_not_integer(self):
        check = {'type': 'json_fields', 'fields': {'count': 1}}
        self.assertFalse(check_response(check, '{"count":true}', 0)['passed'])
        self.assertTrue(check_response(check, '{"count":1}', 0)['passed'])

    def test_nonfinite_json_rejected(self):
        check = {'type': 'json_fields', 'fields': {'count': 1}}
        self.assertFalse(check_response(check, '{"count":1,"bad":NaN}', 0)['passed'])

    def test_duplicate_ids_and_unknown_checks_rejected(self):
        with self.assertRaises(ConfigurationError):
            validate_cases(self.cases + [self.cases[0]])
        self.cases[0]['checks'] = [{'type': 'typo'}]
        with self.assertRaises(ConfigurationError):
            validate_cases(self.cases)

    def test_empty_suite_and_empty_checks_rejected(self):
        with self.assertRaises(ConfigurationError):
            validate_cases([])
        self.cases[0]['checks'] = []
        with self.assertRaises(ConfigurationError):
            validate_cases(self.cases)

    def test_invalid_threshold_rejected(self):
        for value in [-1, 1.1, float('nan')]:
            with self.assertRaises(ConfigurationError):
                evaluate(self.cases, self.good, value)

    def test_reports_escape_untrusted_output(self):
        self.good.responses['refund-policy']['text'] = '<script>alert(1)</script>\x00'
        report = evaluate(self.cases, self.good)
        with tempfile.TemporaryDirectory() as directory:
            write_reports(report, directory)
            html = (Path(directory) / 'report.html').read_text()
            self.assertNotIn('<script>', html)
            self.assertIn('&lt;script&gt;', html)
            xml = ET.parse(Path(directory) / 'junit.xml')
            self.assertEqual(xml.getroot().get('failures'), '1')

    def test_ollama_request_contract(self):
        response = io.BytesIO(b'{"message":{"content":"hello"}}')
        with patch('urllib.request.urlopen', return_value=response) as call:
            text, latency = OllamaProvider('test-model').generate(self.cases[0])
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'http://localhost:11434/api/chat')
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['messages'], self.cases[0]['messages'])
        self.assertEqual(text, 'hello')
        self.assertGreaterEqual(latency, 0)

    def test_ollama_timeout_fails_gate(self):
        with patch('urllib.request.urlopen', side_effect=TimeoutError('timed out')):
            report = evaluate(self.cases[:1], OllamaProvider('test-model'), 0)
        self.assertFalse(report['gate_passed'])
        self.assertEqual(report['provider_errors'], 1)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, expected in [('responses.good.json', 0), ('responses.regression.json', 1)]:
                result = subprocess.run([sys.executable, '-m', 'evalguard', '--responses',
                    'examples/' + filename, '--out', directory], cwd=ROOT, capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)
            result = subprocess.run([sys.executable, '-m', 'evalguard', '--ollama', '--out', directory],
                                    cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
