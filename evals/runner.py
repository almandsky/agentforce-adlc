#!/usr/bin/env python3
"""
Test suite runner for ADLC evals.

Executes eval suites and generates results.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from assertion_labels import extract_label, validate_assertion
from generate import generate_agent
from judge import JudgeResult, create_client, evaluate_test
from test_tags import validate_tags


@dataclass
class TestResult:
    """Result of running a single test case."""
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
    """Result of running a full test suite."""
    suite_name: str
    suite_file: str
    timestamp: str
    tests: list[TestResult]
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
    """Load a suite JSON file."""
    with open(suite_path) as f:
        return json.load(f)


def validate_suite(suite: dict) -> list[str]:
    """Validate suite structure and return any errors."""
    errors = []

    if "name" not in suite:
        errors.append("Missing 'name' field")
    if "tests" not in suite:
        errors.append("Missing 'tests' field")
        return errors

    for i, test in enumerate(suite["tests"]):
        prefix = f"Test {i}"
        if "id" in test:
            prefix = f"Test '{test['id']}'"

        if "id" not in test:
            errors.append(f"{prefix}: Missing 'id' field")
        if "prompt" not in test:
            errors.append(f"{prefix}: Missing 'prompt' field")
        if "assertions" not in test:
            errors.append(f"{prefix}: Missing 'assertions' field")

        # Validate tags
        if "tags" in test:
            tag_result = validate_tags(test["tags"])
            if not tag_result["valid"]:
                errors.append(f"{prefix}: Invalid tags: {tag_result['invalid_tags']}")

        # Validate assertions
        for assertion in test.get("assertions", []):
            result = validate_assertion(assertion)
            if not result["valid"]:
                errors.append(f"{prefix}: Invalid assertion label '{result.get('label', 'unknown')}' - {result.get('suggestion', '')}")

    return errors


def run_test(
    test: dict,
    client: Any,
    model: str = "claude-sonnet-4-20250514",
    agent_content: Optional[str] = None,
    generate_dir: Optional[Path] = None,
    max_turns: int = 6,
    sim_model: str = "claude-haiku-4-5",
    verbose: bool = False,
) -> TestResult:
    """Run a single test case."""
    start_time = datetime.now()

    test_id = test["id"]
    prompt = test["prompt"]
    tags = test.get("tags", [])
    assertions = test.get("assertions", [])
    negative_assertions = test.get("negative_assertions", [])
    total = len(assertions) + len(negative_assertions)

    transcript_path = None
    conversation_path = None
    gen_cost = 0.0
    gen_turns = 0

    if agent_content is None:
        if generate_dir is None:
            err = "No agent content provided and --generate not set"
            return TestResult(
                test_id=test_id, prompt=prompt, tags=tags, agent_content=None,
                assertions_results=[], passed=0, failed=total, total=total,
                score=0.0, error=err,
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

        gen = generate_agent(
            prompt, test_id, generate_dir,
            max_turns=max_turns, sim_model=sim_model, verbose=verbose,
        )
        agent_content = gen.agent_content
        transcript_path = str(gen.transcript_path) if gen.transcript_path else None
        conversation_path = str(generate_dir / test_id / "conversation.log")
        gen_cost = gen.total_cost_usd
        gen_turns = gen.num_turns

        if gen.error or agent_content is None:
            return TestResult(
                test_id=test_id, prompt=prompt, tags=tags,
                agent_content=agent_content, assertions_results=[],
                passed=0, failed=total, total=total, score=0.0,
                error=gen.error or "generation produced no content",
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                transcript_path=transcript_path, conversation_path=conversation_path,
                generation_cost_usd=gen_cost, generation_turns=gen_turns,
            )

    # Evaluate assertions
    results = evaluate_test(
        agent_content,
        assertions,
        negative_assertions,
        client=client,
        model=model,
    )

    # Convert to dicts for serialization
    assertions_results = [asdict(r) for r in results]

    passed = sum(1 for r in results if r.result == "PASS")
    failed = len(results) - passed
    score = passed / len(results) if results else 0.0

    return TestResult(
        test_id=test_id,
        prompt=prompt,
        tags=tags,
        agent_content=agent_content,
        assertions_results=assertions_results,
        passed=passed,
        failed=failed,
        total=len(results),
        score=score,
        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
        transcript_path=transcript_path,
        conversation_path=conversation_path,
        generation_cost_usd=gen_cost,
        generation_turns=gen_turns,
    )


def run_suite(
    suite_path: str,
    test_ids: Optional[list[str]] = None,
    agent_dir: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
    generate_dir: Optional[Path] = None,
    max_turns: int = 6,
    sim_model: str = "claude-haiku-4-5",
    verbose: bool = False,
) -> SuiteResult:
    """
    Run a test suite.

    Args:
        suite_path: Path to suite JSON file
        test_ids: Optional list of specific test IDs to run
        agent_dir: Optional directory containing pre-generated .agent files
        model: Model to use for judge evaluation

    Returns:
        SuiteResult with all test results
    """
    start_time = datetime.now()

    suite = load_suite(suite_path)
    suite_name = suite.get("name", "Unknown Suite")

    # Validate suite
    errors = validate_suite(suite)
    if errors:
        print(f"Suite validation errors:")
        for error in errors:
            print(f"  - {error}")
        # Continue anyway for partial evaluation

    # Create client
    client = create_client()
    if client is None:
        print("Warning: No Anthropic API key found. Using heuristic evaluation only.")

    tests = suite.get("tests", [])

    # Filter to specific test IDs if provided
    if test_ids:
        tests = [t for t in tests if t["id"] in test_ids]

    test_results = []
    for test in tests:
        print(f"Running test: {test['id']}...")

        # Try to load pre-generated agent content
        agent_content = None
        if agent_dir:
            agent_file = Path(agent_dir) / f"{test['id']}.agent"
            if agent_file.exists():
                agent_content = agent_file.read_text()

        result = run_test(
            test, client, model, agent_content,
            generate_dir=generate_dir, max_turns=max_turns,
            sim_model=sim_model, verbose=verbose,
        )
        test_results.append(result)

        # Print progress
        status = "PASS" if result.score == 1.0 else ("PARTIAL" if result.score > 0 else "FAIL")
        print(f"  {status}: {result.passed}/{result.total} assertions passed")
        if result.transcript_path:
            print(f"  transcript:   {result.transcript_path}")
        if result.conversation_path:
            print(f"  conversation: {result.conversation_path}")

    # Aggregate results
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r.score == 1.0)
    failed_tests = total_tests - passed_tests

    total_assertions = sum(r.total for r in test_results)
    passed_assertions = sum(r.passed for r in test_results)
    failed_assertions = total_assertions - passed_assertions

    overall_score = passed_assertions / total_assertions if total_assertions > 0 else 0.0

    # Aggregate by label
    by_label: dict[str, dict] = {}
    for tr in test_results:
        for ar in tr.assertions_results:
            label = extract_label(ar["assertion"])
            if label:
                if label not in by_label:
                    by_label[label] = {"passed": 0, "failed": 0, "total": 0}
                by_label[label]["total"] += 1
                if ar["result"] == "PASS":
                    by_label[label]["passed"] += 1
                else:
                    by_label[label]["failed"] += 1

    # Aggregate by tag
    by_tag: dict[str, dict] = {}
    for tr in test_results:
        for tag in tr.tags:
            if tag not in by_tag:
                by_tag[tag] = {"passed": 0, "failed": 0, "total": 0, "tests": 0}
            by_tag[tag]["tests"] += 1
            by_tag[tag]["total"] += tr.total
            by_tag[tag]["passed"] += tr.passed
            by_tag[tag]["failed"] += tr.failed

    return SuiteResult(
        suite_name=suite_name,
        suite_file=suite_path,
        timestamp=datetime.now().isoformat(),
        tests=[asdict(r) for r in test_results],
        total_tests=total_tests,
        passed_tests=passed_tests,
        failed_tests=failed_tests,
        total_assertions=total_assertions,
        passed_assertions=passed_assertions,
        failed_assertions=failed_assertions,
        overall_score=overall_score,
        by_label=by_label,
        by_tag=by_tag,
        duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
    )


def main():
    parser = argparse.ArgumentParser(description="Run ADLC eval suites")
    parser.add_argument("--suite", "-s", required=True, help="Path to suite JSON file")
    parser.add_argument("--test-ids", "-t", nargs="+", help="Specific test IDs to run")
    parser.add_argument("--agent-dir", "-a", help="Directory with pre-generated .agent files")
    parser.add_argument("--output", "-o", help="Output file for results JSON")
    parser.add_argument("--model", "-m", default="claude-sonnet-4-20250514", help="Model for judge")
    parser.add_argument("--validate-only", action="store_true", help="Only validate suite, don't run")
    parser.add_argument("--generate", nargs="?", const="evals/results/generated",
                        help="Run conversational generation. Optional: output dir")
    parser.add_argument("--max-turns", type=int, default=6, help="Max conversation turns per test")
    parser.add_argument("--sim-model", default="claude-haiku-4-5",
                        help="Model for the simulated user")
    parser.add_argument("--verbose", "-v", action="store_true", help="Stream agent activity")

    args = parser.parse_args()

    # Load and validate
    suite = load_suite(args.suite)
    errors = validate_suite(suite)

    if errors:
        print(f"Validation errors in {args.suite}:")
        for error in errors:
            print(f"  - {error}")
        if args.validate_only:
            sys.exit(1 if errors else 0)

    if args.validate_only:
        print(f"Suite '{suite.get('name')}' validated successfully")
        sys.exit(0)

    # Run suite
    result = run_suite(
        args.suite,
        test_ids=args.test_ids,
        agent_dir=args.agent_dir,
        model=args.model,
        generate_dir=Path(args.generate) if args.generate else None,
        max_turns=args.max_turns,
        sim_model=args.sim_model,
        verbose=args.verbose,
    )

    # Output results
    result_dict = asdict(result)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result_dict, f, indent=2)
        print(f"\nResults written to {args.output}")
    else:
        print("\n" + "=" * 60)
        print(f"Suite: {result.suite_name}")
        print(f"Score: {result.overall_score:.1%}")
        print(f"Tests: {result.passed_tests}/{result.total_tests} passed")
        print(f"Assertions: {result.passed_assertions}/{result.total_assertions} passed")
        print("=" * 60)


if __name__ == "__main__":
    main()
