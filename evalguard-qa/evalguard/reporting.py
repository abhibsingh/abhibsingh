"""Portable JSON, HTML and JUnit XML reports."""
import html
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def xml_safe(value):
    return "".join(c for c in str(value) if c in "\t\n\r" or
                   0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or
                   0x10000 <= ord(c) <= 0x10FFFF)


def write_reports(report, destination):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    suite = ET.Element("testsuite", name="EvalGuard QA", tests=str(report["total"]),
                       failures=str(report["failed"]), errors="0")
    rows = []
    for result in report["results"]:
        details = result["error"] or "\n".join(
            ("PASS " if c["passed"] else "FAIL ") + c["type"] + ": " + c["detail"]
            for c in result["checks"]
        )
        case = ET.SubElement(suite, "testcase", name=xml_safe(result["id"]),
                             classname=xml_safe(result["category"]),
                             time=f"{result['latency_ms'] / 1000:.6f}")
        if not result["passed"]:
            ET.SubElement(case, "failure", message="Evaluation failed").text = xml_safe(details)
        ET.SubElement(case, "system-out").text = xml_safe(result["response"])
        status = "PASS" if result["passed"] else "FAIL"
        rows.append(f'<tr><td>{html.escape(result["id"])}</td><td class="{status}">{status}</td>'
                    f'<td>{result["latency_ms"]:.1f}</td><td><pre>{html.escape(details)}</pre>'
                    f'<details><summary>Response</summary><pre>{html.escape(result["response"])}</pre>'
                    '</details></td></tr>')
    ET.ElementTree(suite).write(root / "junit.xml", encoding="utf-8", xml_declaration=True)
    status = "PASS" if report["gate_passed"] else "FAIL"
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>EvalGuard QA report</title>
<style>body{{font:16px system-ui;margin:3rem auto;max-width:1100px;padding:0 1rem;color:#172b4d}}
header{{border-bottom:4px solid #3157cf;padding-bottom:1rem}}table{{border-collapse:collapse;width:100%}}
th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #ddd}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}.PASS{{color:#126639}}.FAIL{{color:#b42318}}
small{{color:#536078}}</style><header><h1>EvalGuard QA</h1><p>Gate: <b class="{status}">{status}</b>
 · {report["passed"]}/{report["total"]} cases passed · {report["critical_failures"]} critical failures</p>
<small>{html.escape(report["provider"])}</small></header>
<p>Deterministic regression checks; passing does not establish overall model safety or factual accuracy.</p>
<table><thead><tr><th>Case</th><th>Result</th><th>Latency (ms)</th><th>Evidence</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></html>'''
    (root / "report.html").write_text(document, encoding="utf-8")
