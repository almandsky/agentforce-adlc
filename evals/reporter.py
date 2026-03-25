#!/usr/bin/env python3
"""
Results reporter for ADLC evals.

Generates reports from eval results.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_results(results_path: str) -> dict:
    """Load results JSON file."""
    with open(results_path) as f:
        return json.load(f)


def format_score(score: float) -> str:
    """Format score as percentage with color indicator."""
    pct = score * 100
    if pct >= 90:
        return f"{pct:.1f}%"
    elif pct >= 70:
        return f"{pct:.1f}%"
    else:
        return f"{pct:.1f}%"


def print_summary(results: dict) -> None:
    """Print summary report to stdout."""
    print("=" * 70)
    print(f"ADLC Eval Results: {results['suite_name']}")
    print("=" * 70)
    print(f"Timestamp: {results['timestamp']}")
    print(f"Duration: {results['duration_ms']}ms")
    print()

    # Overall score
    score = results["overall_score"]
    print(f"Overall Score: {format_score(score)}")
    print()

    # Test summary
    print("Tests:")
    print(f"  Passed: {results['passed_tests']}/{results['total_tests']}")
    print(f"  Failed: {results['failed_tests']}/{results['total_tests']}")
    print()

    # Assertion summary
    print("Assertions:")
    print(f"  Passed: {results['passed_assertions']}/{results['total_assertions']}")
    print(f"  Failed: {results['failed_assertions']}/{results['total_assertions']}")
    print()

    # By label breakdown
    if results.get("by_label"):
        print("By Label:")
        for label, stats in sorted(results["by_label"].items()):
            label_score = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {label}: {format_score(label_score)} ({stats['passed']}/{stats['total']})")
        print()

    # By tag breakdown
    if results.get("by_tag"):
        print("By Tag:")
        for tag, stats in sorted(results["by_tag"].items()):
            tag_score = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {tag}: {format_score(tag_score)} ({stats['passed']}/{stats['total']} in {stats['tests']} tests)")
        print()

    print("=" * 70)


def print_detailed(results: dict) -> None:
    """Print detailed report with test-level results."""
    print_summary(results)

    print("\nDetailed Test Results:")
    print("-" * 70)

    for test in results["tests"]:
        status = "PASS" if test["score"] == 1.0 else ("PARTIAL" if test["score"] > 0 else "FAIL")
        print(f"\n[{status}] {test['test_id']}")
        print(f"  Score: {format_score(test['score'])} ({test['passed']}/{test['total']})")
        print(f"  Tags: {', '.join(test['tags'])}")

        if test.get("error"):
            print(f"  Error: {test['error']}")

        # Show failed assertions
        failed = [a for a in test["assertions_results"] if a["result"] == "FAIL"]
        if failed:
            print("  Failed assertions:")
            for a in failed:
                print(f"    - {a['assertion']}")
                print(f"      Reason: {a['reason']}")


def print_failures_only(results: dict) -> None:
    """Print only failed assertions."""
    print(f"Failed Assertions for: {results['suite_name']}")
    print("=" * 70)

    failure_count = 0
    for test in results["tests"]:
        failed = [a for a in test["assertions_results"] if a["result"] == "FAIL"]
        if failed:
            print(f"\n{test['test_id']}:")
            for a in failed:
                failure_count += 1
                print(f"  [{a['assertion'].split(']')[0]}] {a['assertion'].split(']')[1].strip()}")
                print(f"    Reason: {a['reason']}")
                if a.get("evidence"):
                    print(f"    Evidence: {a['evidence'][:100]}...")

    print(f"\nTotal failures: {failure_count}")


def generate_markdown_report(results: dict) -> str:
    """Generate markdown report."""
    lines = []
    lines.append(f"# ADLC Eval Results: {results['suite_name']}")
    lines.append("")
    lines.append(f"**Timestamp:** {results['timestamp']}")
    lines.append(f"**Duration:** {results['duration_ms']}ms")
    lines.append("")

    # Overall score
    score = results["overall_score"]
    lines.append(f"## Overall Score: {format_score(score)}")
    lines.append("")

    # Summary table
    lines.append("| Metric | Passed | Total | Score |")
    lines.append("|--------|--------|-------|-------|")
    lines.append(f"| Tests | {results['passed_tests']} | {results['total_tests']} | {format_score(results['passed_tests']/results['total_tests'] if results['total_tests'] > 0 else 0)} |")
    lines.append(f"| Assertions | {results['passed_assertions']} | {results['total_assertions']} | {format_score(score)} |")
    lines.append("")

    # By label
    if results.get("by_label"):
        lines.append("## Results by Label")
        lines.append("")
        lines.append("| Label | Passed | Total | Score |")
        lines.append("|-------|--------|-------|-------|")
        for label, stats in sorted(results["by_label"].items()):
            label_score = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            lines.append(f"| `{label}` | {stats['passed']} | {stats['total']} | {format_score(label_score)} |")
        lines.append("")

    # By tag
    if results.get("by_tag"):
        lines.append("## Results by Tag")
        lines.append("")
        lines.append("| Tag | Tests | Passed | Total | Score |")
        lines.append("|-----|-------|--------|-------|-------|")
        for tag, stats in sorted(results["by_tag"].items()):
            tag_score = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            lines.append(f"| `{tag}` | {stats['tests']} | {stats['passed']} | {stats['total']} | {format_score(tag_score)} |")
        lines.append("")

    # Test details
    lines.append("## Test Details")
    lines.append("")

    for test in results["tests"]:
        status = "PASS" if test["score"] == 1.0 else ("PARTIAL" if test["score"] > 0 else "FAIL")
        emoji = {"PASS": ":white_check_mark:", "PARTIAL": ":warning:", "FAIL": ":x:"}[status]

        lines.append(f"### {emoji} {test['test_id']}")
        lines.append("")
        lines.append(f"**Score:** {format_score(test['score'])} ({test['passed']}/{test['total']})")
        lines.append(f"**Tags:** `{'`, `'.join(test['tags'])}`")
        lines.append("")

        if test.get("error"):
            lines.append(f"> **Error:** {test['error']}")
            lines.append("")

        # Assertions table
        lines.append("| Assertion | Result | Reason |")
        lines.append("|-----------|--------|--------|")
        for a in test["assertions_results"]:
            result_emoji = ":white_check_mark:" if a["result"] == "PASS" else ":x:"
            assertion_text = a["assertion"].replace("|", "\\|")
            reason = a["reason"].replace("|", "\\|")[:80]
            lines.append(f"| {assertion_text} | {result_emoji} | {reason} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate ADLC eval reports")
    parser.add_argument("results", help="Path to results JSON file")
    parser.add_argument("--format", "-f", choices=["summary", "detailed", "failures", "markdown", "json"],
                        default="summary", help="Report format")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    args = parser.parse_args()

    results = load_results(args.results)

    # Generate report
    if args.format == "summary":
        print_summary(results)
    elif args.format == "detailed":
        print_detailed(results)
    elif args.format == "failures":
        print_failures_only(results)
    elif args.format == "markdown":
        md = generate_markdown_report(results)
        if args.output:
            with open(args.output, "w") as f:
                f.write(md)
            print(f"Markdown report written to {args.output}")
        else:
            print(md)
    elif args.format == "json":
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
        else:
            print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
