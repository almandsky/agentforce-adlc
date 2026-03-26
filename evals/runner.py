#!/usr/bin/env python3
"""
ADLC eval suite runner.

Loads a suite JSON, optionally generates agents via the conversational
harness, runs LLM-as-judge on each assertion, and writes results.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from harness import DEFAULT_MAX_TURNS, DEFAULT_SIM_MODEL, default_output_dir, simulate_conversation
from judge import DEFAULT_JUDGE_MODEL, create_client, evaluate_test
from reporter import print_summary
from taxonomy import extract_label, validate_assertion, validate_tags


@dataclass
class TestResult:
    test_id: str
    prompt: str
    tags: list[str]
    agent_content: Optional[str]
    assertions_results: list[dict]
    passed: int
    failed: int
    total: int
    score: float
    error: Optional[str] = None
    duration_ms: int = 0
    transcript_path: Optional[str] = None
    generation_cost_usd: float = 0.0
    generation_turns: int = 0
    conversation_path: Optional[str] = None


@dataclass
class SuiteResult:
    suite_name: str
    suite_file: str
    timestamp: str
    tests: list[dict]
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_assertions: int
    passed_assertions: int
    failed_assertions: int
    overall_score: float
    by_label: dict = field(default_factory=dict)
    by_tag: dict = field(default_factory=dict)
    duration_ms: int = 0


def load_suite(suite_path: str) -> dict:
    with open(suite_path) as f:
        return json.load(f)


def _read_process_log(test_dir: Path) -> Optional[str]:
    """Concatenate conversation.log + activity.log for process:* judging."""
    conv = test_dir / "conversation.log"
    act = test_dir / "activity.log"
    if not conv.exists() and not act.exists():
        return None
    parts = []
    if conv.exists():
        parts.append("=== CONVERSATION ===\n" + conv.read_text())
    if act.exists():
        parts.append("=== ACTIVITY (tool calls) ===\n" + act.read_text())
    return "\n\n".join(parts)


def validate_suite(suite: dict) -> list[str]:
    errors = []
    if "name" not in suite:
        errors.append("Missing 'name' field")
    if "tests" not in suite:
        errors.append("Missing 'tests' field")
        return errors

    for i, test in enumerate(suite["tests"]):
        prefix = f"Test '{test['id']}'" if "id" in test else f"Test {i}"
        for req in ("id", "prompt", "assertions"):
            if req not in test:
                errors.append(f"{prefix}: Missing '{req}' field")

        if "tags" in test:
            r = validate_tags(test["tags"])
            if not r["valid"]:
                errors.append(f"{prefix}: Invalid tags: {r['invalid_tags']}")

        for a in test.get("assertions", []):
            r = validate_assertion(a)
            if not r["valid"]:
                errors.append(f"{prefix}: Invalid assertion label "
                              f"'{r.get('label', '?')}' - {r.get('suggestion', '')}")
    return errors


def run_test(
    test: dict,
    client: Any,
    model: str,
    agent_content: Optional[str],
    generate_dir: Optional[Path],
    max_turns: int,
    sim_model: str,
    verbose: bool,
) -> TestResult:
    start = datetime.now()
    test_id = test["id"]
    prompt = test["prompt"]
    goal = test.get("goal")
    tags = test.get("tags", [])
    assertions = test.get("assertions", [])
    negative = test.get("negative_assertions", [])
    total = len(assertions) + len(negative)

    def _elapsed_ms() -> int:
        return int((datetime.now() - start).total_seconds() * 1000)

    def _fail(err: str, **kw) -> TestResult:
        return TestResult(
            test_id=test_id, prompt=prompt, tags=tags, agent_content=agent_content,
            assertions_results=[], passed=0, failed=total, total=total,
            score=0.0, error=err, duration_ms=_elapsed_ms(), **kw,
        )

    transcript_path = conversation_path = None
    process_log: Optional[str] = None
    gen_cost = 0.0
    gen_turns = 0

    if agent_content is None:
        if generate_dir is None:
            return _fail("No agent content provided and --generate not set")

        gen = simulate_conversation(
            prompt, test_id, generate_dir, goal=goal,
            max_turns=max_turns, sim_model=sim_model, verbose=verbose,
        )
        agent_content = gen.agent_content
        transcript_path = str(gen.transcript_path) if gen.transcript_path else None
        test_dir = generate_dir / test_id
        conversation_path = str(test_dir / "conversation.log")
        gen_cost = gen.total_cost_usd
        gen_turns = gen.num_turns

        if gen.error or agent_content is None:
            return _fail(
                gen.error or "generation produced no content",
                transcript_path=transcript_path, conversation_path=conversation_path,
                generation_cost_usd=gen_cost, generation_turns=gen_turns,
            )

        process_log = _read_process_log(test_dir)

    artifacts = {"agent": agent_content}
    if process_log:
        artifacts["process"] = process_log

    results = evaluate_test(artifacts, assertions, negative, client=client, model=model)
    assertions_results = [asdict(r) for r in results]
    passed = sum(1 for r in results if r.result == "PASS")

    return TestResult(
        test_id=test_id, prompt=prompt, tags=tags, agent_content=agent_content,
        assertions_results=assertions_results,
        passed=passed, failed=len(results) - passed, total=len(results),
        score=passed / len(results) if results else 0.0,
        duration_ms=_elapsed_ms(),
        transcript_path=transcript_path, conversation_path=conversation_path,
        generation_cost_usd=gen_cost, generation_turns=gen_turns,
    )


def run_suite(
    suite_path: str,
    suite: dict,
    test_ids: Optional[list[str]] = None,
    agent_dir: Optional[str] = None,
    model: str = DEFAULT_JUDGE_MODEL,
    generate_dir: Optional[Path] = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    sim_model: str = DEFAULT_SIM_MODEL,
    verbose: bool = False,
) -> SuiteResult:
    start = datetime.now()
    client = create_client()

    tests = suite.get("tests", [])
    if test_ids:
        tests = [t for t in tests if t["id"] in test_ids]

    test_results: list[TestResult] = []
    for test in tests:
        print(f"Running test: {test['id']}...")

        agent_content = None
        if agent_dir:
            f = Path(agent_dir) / f"{test['id']}.agent"
            if f.exists():
                agent_content = f.read_text()

        r = run_test(test, client, model, agent_content, generate_dir,
                     max_turns, sim_model, verbose)
        test_results.append(r)

        status = "PASS" if r.score == 1.0 else ("PARTIAL" if r.score > 0 else "FAIL")
        print(f"  {status}: {r.passed}/{r.total} assertions passed")
        if r.transcript_path:
            print(f"  transcript:   {r.transcript_path}")
        if r.conversation_path:
            print(f"  conversation: {r.conversation_path}")

    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r.score == 1.0)
    total_a = sum(r.total for r in test_results)
    passed_a = sum(r.passed for r in test_results)

    by_label: dict[str, dict] = {}
    for tr in test_results:
        for ar in tr.assertions_results:
            label = extract_label(ar["assertion"])
            if label:
                s = by_label.setdefault(label, {"passed": 0, "failed": 0, "total": 0})
                s["total"] += 1
                s["passed" if ar["result"] == "PASS" else "failed"] += 1

    by_tag: dict[str, dict] = {}
    for tr in test_results:
        for tag in tr.tags:
            s = by_tag.setdefault(tag, {"passed": 0, "failed": 0, "total": 0, "tests": 0})
            s["tests"] += 1
            s["total"] += tr.total
            s["passed"] += tr.passed
            s["failed"] += tr.failed

    return SuiteResult(
        suite_name=suite.get("name", "Unknown Suite"),
        suite_file=suite_path,
        timestamp=datetime.now().isoformat(),
        tests=[asdict(r) for r in test_results],
        total_tests=total_tests,
        passed_tests=passed_tests,
        failed_tests=total_tests - passed_tests,
        total_assertions=total_a,
        passed_assertions=passed_a,
        failed_assertions=total_a - passed_a,
        overall_score=passed_a / total_a if total_a else 0.0,
        by_label=by_label,
        by_tag=by_tag,
        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
    )


def main():
    p = argparse.ArgumentParser(description="Run ADLC eval suites")
    p.add_argument("--suite", "-s", required=True, help="Path to suite JSON file")
    p.add_argument("--test-ids", "-t", nargs="+", help="Specific test IDs to run")
    p.add_argument("--agent-dir", "-a", help="Directory with pre-generated .agent files")
    p.add_argument("--output", "-o", help="Output file for results JSON")
    p.add_argument("--model", "-m", default=DEFAULT_JUDGE_MODEL, help="Model for judge")
    p.add_argument("--validate-only", action="store_true", help="Only validate suite, don't run")
    p.add_argument("--generate", nargs="?", const="<timestamped>",
                   help="Run conversational generation. Optional: output dir "
                        "(default: evals/results/run-<timestamp>)")
    p.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS,
                   help="Max conversation turns per test")
    p.add_argument("--sim-model", default=DEFAULT_SIM_MODEL,
                   help="Model for the simulated user")
    p.add_argument("--verbose", "-v", action="store_true", help="Stream agent activity")
    args = p.parse_args()

    suite = load_suite(args.suite)
    errors = validate_suite(suite)
    if errors:
        print(f"Validation errors in {args.suite}:")
        for e in errors:
            print(f"  - {e}")
        if args.validate_only:
            sys.exit(1)

    if args.validate_only:
        print(f"Suite '{suite.get('name')}' validated successfully")
        sys.exit(0)

    generate_dir = None
    if args.generate:
        generate_dir = (default_output_dir() if args.generate == "<timestamped>"
                        else Path(args.generate))
        print(f"Generation logs: {generate_dir}/")

    result = run_suite(
        args.suite, suite, test_ids=args.test_ids, agent_dir=args.agent_dir,
        model=args.model, generate_dir=generate_dir,
        max_turns=args.max_turns, sim_model=args.sim_model, verbose=args.verbose,
    )

    result_dict = asdict(result)
    output_path = args.output
    if not output_path and generate_dir:
        output_path = generate_dir / "eval_results.json"

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result_dict, f, indent=2)
        print(f"\nResults written to {output_path}")

    print()
    print_summary(result_dict)


if __name__ == "__main__":
    main()
