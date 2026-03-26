#!/usr/bin/env python3
"""
Report formatting for ADLC eval results.
"""

import argparse
import json


def _pct(score: float) -> str:
    return f"{score * 100:.1f}%"


def print_summary(results: dict) -> None:
    print("=" * 70)
    print(f"ADLC Eval Results: {results['suite_name']}")
    print("=" * 70)
    print(f"Timestamp: {results['timestamp']}")
    print(f"Duration: {results['duration_ms']}ms")
    print()
    print(f"Overall Score: {_pct(results['overall_score'])}")
    print()
    print("Tests:")
    print(f"  Passed: {results['passed_tests']}/{results['total_tests']}")
    print(f"  Failed: {results['failed_tests']}/{results['total_tests']}")
    print()
    print("Assertions:")
    print(f"  Passed: {results['passed_assertions']}/{results['total_assertions']}")
    print(f"  Failed: {results['failed_assertions']}/{results['total_assertions']}")
    print()

    if results.get("by_label"):
        print("By Label:")
        for label, s in sorted(results["by_label"].items()):
            score = s["passed"] / s["total"] if s["total"] else 0
            print(f"  {label}: {_pct(score)} ({s['passed']}/{s['total']})")
        print()

    if results.get("by_tag"):
        print("By Tag:")
        for tag, s in sorted(results["by_tag"].items()):
            score = s["passed"] / s["total"] if s["total"] else 0
            print(f"  {tag}: {_pct(score)} ({s['passed']}/{s['total']} in {s['tests']} tests)")
        print()

    print("=" * 70)


def print_detailed(results: dict) -> None:
    print_summary(results)
    print("\nDetailed Test Results:")
    print("-" * 70)

    for test in results["tests"]:
        status = "PASS" if test["score"] == 1.0 else ("PARTIAL" if test["score"] > 0 else "FAIL")
        print(f"\n[{status}] {test['test_id']}")
        print(f"  Score: {_pct(test['score'])} ({test['passed']}/{test['total']})")
        print(f"  Tags: {', '.join(test['tags'])}")
        if test.get("error"):
            print(f"  Error: {test['error']}")

        failed = [a for a in test["assertions_results"] if a["result"] == "FAIL"]
        if failed:
            print("  Failed assertions:")
            for a in failed:
                print(f"    - {a['assertion']}")
                print(f"      Reason: {a['reason']}")


def print_failures(results: dict) -> None:
    print(f"Failed Assertions for: {results['suite_name']}")
    print("=" * 70)

    count = 0
    for test in results["tests"]:
        failed = [a for a in test["assertions_results"] if a["result"] == "FAIL"]
        if failed:
            print(f"\n{test['test_id']}:")
            for a in failed:
                count += 1
                parts = a["assertion"].split("]", 1)
                print(f"  [{parts[0].lstrip('[')}] {parts[1].strip() if len(parts) > 1 else ''}")
                print(f"    Reason: {a['reason']}")
                if a.get("evidence"):
                    print(f"    Evidence: {a['evidence'][:100]}...")

    print(f"\nTotal failures: {count}")


def generate_markdown(results: dict) -> str:
    lines = [
        f"# ADLC Eval Results: {results['suite_name']}",
        "",
        f"**Timestamp:** {results['timestamp']}",
        f"**Duration:** {results['duration_ms']}ms",
        "",
        f"## Overall Score: {_pct(results['overall_score'])}",
        "",
        "| Metric | Passed | Total | Score |",
        "|--------|--------|-------|-------|",
    ]
    tt = results["total_tests"]
    lines.append(f"| Tests | {results['passed_tests']} | {tt} | "
                 f"{_pct(results['passed_tests'] / tt if tt else 0)} |")
    lines.append(f"| Assertions | {results['passed_assertions']} | "
                 f"{results['total_assertions']} | {_pct(results['overall_score'])} |")
    lines.append("")

    if results.get("by_label"):
        lines += ["## Results by Label", "",
                  "| Label | Passed | Total | Score |",
                  "|-------|--------|-------|-------|"]
        for label, s in sorted(results["by_label"].items()):
            score = s["passed"] / s["total"] if s["total"] else 0
            lines.append(f"| `{label}` | {s['passed']} | {s['total']} | {_pct(score)} |")
        lines.append("")

    if results.get("by_tag"):
        lines += ["## Results by Tag", "",
                  "| Tag | Tests | Passed | Total | Score |",
                  "|-----|-------|--------|-------|-------|"]
        for tag, s in sorted(results["by_tag"].items()):
            score = s["passed"] / s["total"] if s["total"] else 0
            lines.append(f"| `{tag}` | {s['tests']} | {s['passed']} | {s['total']} | {_pct(score)} |")
        lines.append("")

    lines += ["## Test Details", ""]
    for test in results["tests"]:
        status = "PASS" if test["score"] == 1.0 else ("PARTIAL" if test["score"] > 0 else "FAIL")
        emoji = {"PASS": ":white_check_mark:", "PARTIAL": ":warning:", "FAIL": ":x:"}[status]
        lines += [
            f"### {emoji} {test['test_id']}", "",
            f"**Score:** {_pct(test['score'])} ({test['passed']}/{test['total']})",
            f"**Tags:** `{'`, `'.join(test['tags'])}`", "",
        ]
        if test.get("error"):
            lines += [f"> **Error:** {test['error']}", ""]

        lines += ["| Assertion | Result | Reason |",
                  "|-----------|--------|--------|"]
        for a in test["assertions_results"]:
            mark = ":white_check_mark:" if a["result"] == "PASS" else ":x:"
            assertion = a["assertion"].replace("|", "\\|")
            reason = a["reason"].replace("|", "\\|")[:80]
            lines.append(f"| {assertion} | {mark} | {reason} |")
        lines.append("")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Generate ADLC eval reports")
    p.add_argument("results", help="Path to results JSON file")
    p.add_argument("--format", "-f", default="summary",
                   choices=["summary", "detailed", "failures", "markdown", "json"])
    p.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = p.parse_args()

    with open(args.results) as f:
        results = json.load(f)

    if args.format == "summary":
        print_summary(results)
    elif args.format == "detailed":
        print_detailed(results)
    elif args.format == "failures":
        print_failures(results)
    elif args.format == "markdown":
        md = generate_markdown(results)
        if args.output:
            with open(args.output, "w") as f:
                f.write(md)
            print(f"Markdown report written to {args.output}")
        else:
            print(md)
    elif args.format == "json":
        out = json.dumps(results, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(out)
        else:
            print(out)


if __name__ == "__main__":
    main()
