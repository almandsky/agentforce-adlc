#!/usr/bin/env python3
"""Generate metadata stubs (Flow XML, Apex classes) for missing .agent file targets.

Reads discovery report or .agent file, generates stubs for targets not found in the org.

Usage:
    python3 scripts/scaffold.py --agent-file path/to/Agent.agent -o OrgAlias --output-dir force-app/main/default
    python3 scripts/scaffold.py --agent-file path/to/Agent.agent --all --output-dir force-app/main/default
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure the parent directory is in sys.path for package imports
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.discover import DiscoveryReport, TargetStatus, discover, extract_actions
from scripts.generators.flow_xml import generate_flow_xml
from scripts.generators.apex_stub import generate_apex_class, generate_apex_meta_xml
from scripts.generators.permission_set_xml import generate_permission_set_xml
from scripts.org_describe import describe_sobject, match_fields


@dataclass
class ScaffoldResult:
    """Result of scaffolding operations."""
    files_created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def scaffold(
    report: DiscoveryReport,
    output_dir: Path,
    agent_file: Path | None = None,
    target_org: str | None = None,
) -> ScaffoldResult:
    """Generate stubs for all missing targets in a discovery report.

    Args:
        report: Discovery report with found/missing targets.
        output_dir: Base output directory (e.g. force-app/main/default).
        agent_file: Path to .agent file (for extracting action I/O definitions).
        target_org: Org alias (for smart scaffold with SObject field mapping).

    Returns:
        ScaffoldResult with created files and warnings.
    """
    result = ScaffoldResult()

    # Load action definitions from .agent file for input/output info
    actions = {}
    if agent_file and agent_file.exists():
        for action in extract_actions(agent_file):
            if action.get("target_name"):
                actions[action["target_name"]] = action

    apex_classes = []

    for target in report.missing:
        if target.target_type == "flow":
            _scaffold_flow(target, output_dir, actions, target_org, result)
        elif target.target_type == "apex":
            _scaffold_apex(target, output_dir, actions, target_org, result)
            apex_classes.append(target.target_name)
        elif target.target_type == "retriever":
            result.warnings.append(
                f"Retriever '{target.target_name}' must be created manually in "
                f"Setup → Data Cloud → Data Spaces → Knowledge"
            )

    # Generate permission set if any Apex classes were scaffolded
    if apex_classes:
        _scaffold_permission_set(apex_classes, output_dir, result)

    return result


def scaffold_all(
    agent_file: Path,
    output_dir: Path,
    target_org: str | None = None,
) -> ScaffoldResult:
    """Scaffold all targets without org check (generate stubs for everything)."""
    from scripts.discover import extract_targets

    report = DiscoveryReport()
    for uri, ttype, tname in extract_targets(agent_file):
        report.targets.append(TargetStatus(
            agent_file=str(agent_file),
            target=uri,
            target_type=ttype,
            target_name=tname,
            found=False,  # Treat all as missing
        ))

    return scaffold(report, output_dir, agent_file, target_org)


def _scaffold_flow(
    target: TargetStatus,
    output_dir: Path,
    actions: dict,
    target_org: str | None,
    result: ScaffoldResult,
) -> None:
    """Generate Flow XML stub."""
    flow_dir = output_dir / "flows"
    flow_dir.mkdir(parents=True, exist_ok=True)

    action_def = actions.get(target.target_name, {})
    inputs = action_def.get("inputs", [])
    outputs = action_def.get("outputs", [])

    xml = generate_flow_xml(target.target_name, inputs, outputs)

    flow_path = flow_dir / f"{target.target_name}.flow-meta.xml"
    flow_path.write_text(xml, encoding="utf-8")
    result.files_created.append(flow_path)


def _scaffold_apex(
    target: TargetStatus,
    output_dir: Path,
    actions: dict,
    target_org: str | None,
    result: ScaffoldResult,
) -> None:
    """Generate Apex class + test class + meta XMLs."""
    classes_dir = output_dir / "classes"
    classes_dir.mkdir(parents=True, exist_ok=True)

    action_def = actions.get(target.target_name, {})
    inputs = action_def.get("inputs", [])
    outputs = action_def.get("outputs", [])

    # Main class
    cls_code = generate_apex_class(target.target_name, inputs, outputs)
    cls_path = classes_dir / f"{target.target_name}.cls"
    cls_path.write_text(cls_code, encoding="utf-8")
    result.files_created.append(cls_path)

    # Meta XML
    meta_xml = generate_apex_meta_xml()
    meta_path = classes_dir / f"{target.target_name}.cls-meta.xml"
    meta_path.write_text(meta_xml, encoding="utf-8")
    result.files_created.append(meta_path)

    # Test class
    test_name = f"{target.target_name}Test"
    test_code = _generate_test_class(test_name, target.target_name, inputs)
    test_path = classes_dir / f"{test_name}.cls"
    test_path.write_text(test_code, encoding="utf-8")
    result.files_created.append(test_path)

    # Test meta XML
    test_meta_path = classes_dir / f"{test_name}.cls-meta.xml"
    test_meta_path.write_text(meta_xml, encoding="utf-8")
    result.files_created.append(test_meta_path)


def _generate_test_class(test_name: str, class_name: str, inputs: list[dict]) -> str:
    """Generate a minimal test class for an Apex stub."""
    lines = [
        f"@isTest",
        f"private class {test_name} {{",
        f"    @isTest",
        f"    static void testInvoke() {{",
        f"        {class_name}.Request req = new {class_name}.Request();",
    ]
    for inp in inputs:
        default = "'test'" if inp.get("type") in ("string", "id") else "0" if inp.get("type") == "number" else "false"
        lines.append(f"        req.{inp['name']} = {default};")
    lines.extend([
        f"        List<{class_name}.Response> results = {class_name}.invoke(",
        f"            new List<{class_name}.Request>{{ req }}",
        f"        );",
        f"        System.assertNotEquals(null, results, 'Expected non-null response');",
        f"        System.assertEquals(1, results.size(), 'Expected one response');",
        f"    }}",
        f"}}",
    ])
    return "\n".join(lines) + "\n"


def _scaffold_permission_set(
    apex_classes: list[str],
    output_dir: Path,
    result: ScaffoldResult,
) -> None:
    """Generate permission set granting access to scaffolded Apex classes."""
    perm_dir = output_dir / "permissionsets"
    perm_dir.mkdir(parents=True, exist_ok=True)

    # Include both classes and their test classes
    all_classes = []
    for cls in apex_classes:
        all_classes.append(cls)
        all_classes.append(f"{cls}Test")

    xml = generate_permission_set_xml("Agent_Action_Access", all_classes)
    perm_path = perm_dir / "Agent_Action_Access.permissionset-meta.xml"
    perm_path.write_text(xml, encoding="utf-8")
    result.files_created.append(perm_path)


def print_result(result: ScaffoldResult) -> None:
    """Print scaffold results."""
    if result.files_created:
        print(f"\n✅ Created {len(result.files_created)} file(s):")
        for f in result.files_created:
            print(f"   {f}")

    if result.warnings:
        print(f"\n⚠️  Warnings:")
        for w in result.warnings:
            print(f"   {w}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Scaffold metadata stubs for missing .agent targets")
    parser.add_argument("--agent-file", type=Path, required=True, help="Path to .agent file")
    parser.add_argument("-o", "--target-org", help="Salesforce org alias (for discovery)")
    parser.add_argument("--output-dir", type=Path, default=Path("force-app/main/default"), help="Output directory")
    parser.add_argument("--all", action="store_true", help="Scaffold all targets (skip org check)")
    args = parser.parse_args()

    if not args.agent_file.exists():
        print(f"Error: {args.agent_file} not found", file=sys.stderr)
        sys.exit(1)

    if args.all:
        result = scaffold_all(args.agent_file, args.output_dir, args.target_org)
    else:
        if not args.target_org:
            print("Error: --target-org required (or use --all to skip org check)", file=sys.stderr)
            sys.exit(1)
        report = discover(args.agent_file, args.target_org)
        result = scaffold(report, args.output_dir, args.agent_file, args.target_org)

    print_result(result)


if __name__ == "__main__":
    main()
