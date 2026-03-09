#!/usr/bin/env python3
"""Discover which .agent file targets (flows, apex classes, retrievers) exist in a Salesforce org.

Reads .agent files to extract target: values (flow://, apex://, retriever://),
queries the org via sf CLI, and reports found/missing targets with fuzzy suggestions.

Usage:
    python3 scripts/discover.py --agent-file path/to/Agent.agent -o OrgAlias
    python3 scripts/discover.py --agent-dir force-app/main/default/aiAuthoringBundles -o OrgAlias
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Suggestion:
    """A similar resource found in the org."""
    name: str
    similarity: float  # 0.0–1.0


@dataclass
class TargetStatus:
    """Status of one .agent target."""
    agent_file: str
    target: str           # e.g. "flow://Get_Order_Status"
    target_type: str      # "flow", "apex", "retriever"
    target_name: str      # "Get_Order_Status"
    found: bool = False
    details: str = ""
    suggestions: list[Suggestion] = field(default_factory=list)


@dataclass
class DiscoveryReport:
    """Collection of target statuses."""
    targets: list[TargetStatus] = field(default_factory=list)

    @property
    def found(self) -> list[TargetStatus]:
        return [t for t in self.targets if t.found]

    @property
    def missing(self) -> list[TargetStatus]:
        return [t for t in self.targets if not t.found]

    @property
    def all_found(self) -> bool:
        return all(t.found for t in self.targets)


def extract_targets(agent_file: Path) -> list[tuple[str, str, str]]:
    """Extract target: values from an .agent file.

    Returns list of (target_uri, target_type, target_name) tuples.
    e.g. ("flow://Get_Order_Status", "flow", "Get_Order_Status")
    """
    content = agent_file.read_text(encoding="utf-8")
    targets = []
    # Match target: "flow://Name" or target: "apex://Name" or target: "retriever://Name"
    for match in re.finditer(r'target:\s*"?(flow|apex|retriever)://([^"\s]+)"?', content):
        target_type = match.group(1)
        target_name = match.group(2)
        target_uri = f"{target_type}://{target_name}"
        targets.append((target_uri, target_type, target_name))
    return targets


def extract_actions(agent_file: Path) -> list[dict]:
    """Extract action definitions from an .agent file for scaffolding.

    Returns list of dicts with keys: name, target, target_type, target_name, inputs, outputs.
    """
    content = agent_file.read_text(encoding="utf-8")
    actions = []
    # Simple regex-based extraction of action blocks
    # Matches patterns like:
    #   action_name:
    #       ...
    #       target: "flow://Name"
    current_action = None
    current_inputs = []
    current_outputs = []
    in_inputs = False
    in_outputs = False

    for line in content.splitlines():
        stripped = line.strip()

        # Detect target line
        target_match = re.match(r'target:\s*"?(flow|apex|retriever)://([^"\s]+)"?', stripped)
        if target_match and current_action:
            current_action["target_type"] = target_match.group(1)
            current_action["target_name"] = target_match.group(2)
            current_action["target"] = f"{target_match.group(1)}://{target_match.group(2)}"

        # Detect inputs/outputs sections
        if stripped == "inputs:":
            in_inputs = True
            in_outputs = False
            continue
        elif stripped == "outputs:":
            in_outputs = True
            in_inputs = False
            continue

        # Detect action start (indented name followed by colon, with description)
        action_match = re.match(r'^(\t{2}|\s{8})(\w+):\s*$', line)
        if action_match and not in_inputs and not in_outputs:
            # Save previous action
            if current_action and current_action.get("target"):
                current_action["inputs"] = current_inputs
                current_action["outputs"] = current_outputs
                actions.append(current_action)
            current_action = {"name": action_match.group(2)}
            current_inputs = []
            current_outputs = []
            in_inputs = False
            in_outputs = False

        # Collect input/output parameters
        param_match = re.match(r'^\s+(\w+):\s*(string|number|boolean|date|datetime|id|object)', stripped)
        if param_match:
            param = {"name": param_match.group(1), "type": param_match.group(2)}
            if in_inputs:
                current_inputs.append(param)
            elif in_outputs:
                current_outputs.append(param)

    # Don't forget the last action
    if current_action and current_action.get("target"):
        current_action["inputs"] = current_inputs
        current_action["outputs"] = current_outputs
        actions.append(current_action)

    return actions


def _query_org(query: str, target_org: str) -> list[dict]:
    """Run SOQL query via sf CLI."""
    cmd = ["sf", "data", "query", "--query", query, "-o", target_org, "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout)
        return data.get("result", {}).get("records", [])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _check_flows(names: list[str], target_org: str) -> dict[str, bool]:
    """Check which flows exist in the org."""
    records = _query_org(
        "SELECT ApiName FROM FlowDefinitionView WHERE IsActive = true",
        target_org,
    )
    org_flows = {r["ApiName"] for r in records if "ApiName" in r}
    return {name: name in org_flows for name in names}


def _check_apex(names: list[str], target_org: str) -> dict[str, bool]:
    """Check which Apex classes exist in the org."""
    records = _query_org(
        "SELECT Name FROM ApexClass WHERE Status = 'Active'",
        target_org,
    )
    org_classes = {r["Name"] for r in records if "Name" in r}
    return {name: name in org_classes for name in names}


def _check_retrievers(names: list[str], target_org: str) -> dict[str, bool]:
    """Check which retrievers (DataKnowledgeSpace) exist in the org."""
    records = _query_org(
        "SELECT DeveloperName FROM DataKnowledgeSpace",
        target_org,
    )
    org_retrievers = {r["DeveloperName"] for r in records if "DeveloperName" in r}
    return {name: name in org_retrievers for name in names}


def _suggest_similar(name: str, available: list[str], threshold: float = 0.4) -> list[Suggestion]:
    """Find similar names in the org using fuzzy matching."""
    suggestions = []
    name_lower = name.lower()
    name_tokens = set(re.split(r"[_\s]|(?<=[a-z])(?=[A-Z])", name))

    for candidate in available:
        # Sequence matching
        seq_score = difflib.SequenceMatcher(None, name_lower, candidate.lower()).ratio()

        # Jaccard keyword overlap
        cand_tokens = set(re.split(r"[_\s]|(?<=[a-z])(?=[A-Z])", candidate))
        if name_tokens and cand_tokens:
            jaccard = len(name_tokens & cand_tokens) / len(name_tokens | cand_tokens)
        else:
            jaccard = 0.0

        score = max(seq_score, jaccard)
        if score >= threshold:
            suggestions.append(Suggestion(name=candidate, similarity=round(score, 2)))

    return sorted(suggestions, key=lambda s: s.similarity, reverse=True)[:3]


def discover(agent_file: Path, target_org: str) -> DiscoveryReport:
    """Run discovery for a single .agent file."""
    report = DiscoveryReport()
    raw_targets = extract_targets(agent_file)

    if not raw_targets:
        return report

    # Group by type
    by_type: dict[str, list[tuple[str, str]]] = {"flow": [], "apex": [], "retriever": []}
    for uri, ttype, tname in raw_targets:
        by_type.setdefault(ttype, []).append((uri, tname))

    # Check each type
    checkers = {
        "flow": (_check_flows, "SELECT ApiName FROM FlowDefinitionView WHERE IsActive = true", "ApiName"),
        "apex": (_check_apex, "SELECT Name FROM ApexClass WHERE Status = 'Active'", "Name"),
        "retriever": (_check_retrievers, "SELECT DeveloperName FROM DataKnowledgeSpace", "DeveloperName"),
    }

    for ttype, targets in by_type.items():
        if not targets:
            continue

        checker_fn, query, field_name = checkers[ttype]
        names = [t[1] for t in targets]
        found_map = checker_fn(names, target_org)

        # Get all available resources for fuzzy matching
        all_records = _query_org(query, target_org)
        available = [r[field_name] for r in all_records if field_name in r]

        for uri, name in targets:
            status = TargetStatus(
                agent_file=str(agent_file),
                target=uri,
                target_type=ttype,
                target_name=name,
                found=found_map.get(name, False),
            )
            if not status.found:
                status.suggestions = _suggest_similar(name, available)
            report.targets.append(status)

    return report


def discover_dir(agent_dir: Path, target_org: str) -> DiscoveryReport:
    """Run discovery for all .agent files in a directory."""
    combined = DiscoveryReport()
    for agent_file in sorted(agent_dir.rglob("*.agent")):
        sub_report = discover(agent_file, target_org)
        combined.targets.extend(sub_report.targets)
    return combined


def print_report(report: DiscoveryReport) -> None:
    """Print a human-readable discovery report."""
    if not report.targets:
        print("No targets found in .agent file(s).")
        return

    print(f"\n{'=' * 60}")
    print(f"Discovery Report: {len(report.targets)} target(s)")
    print(f"{'=' * 60}")

    # Found targets
    if report.found:
        print(f"\n✅ Found ({len(report.found)}):")
        for t in report.found:
            print(f"   {t.target}")

    # Missing targets
    if report.missing:
        print(f"\n❌ Missing ({len(report.missing)}):")
        for t in report.missing:
            print(f"   {t.target}")
            for s in t.suggestions:
                print(f"      💡 Did you mean: {s.name} ({s.similarity:.0%} match)?")

    print(f"\n{'=' * 60}")
    if report.all_found:
        print("All targets found in org.")
    else:
        print(f"{len(report.missing)} target(s) missing. Run /adlc-scaffold to generate stubs.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Discover .agent file targets in a Salesforce org")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent-file", type=Path, help="Path to a single .agent file")
    group.add_argument("--agent-dir", type=Path, help="Directory containing .agent files")
    parser.add_argument("-o", "--target-org", required=True, help="Salesforce org alias")
    args = parser.parse_args()

    if args.agent_file:
        if not args.agent_file.exists():
            print(f"Error: {args.agent_file} not found", file=sys.stderr)
            sys.exit(1)
        report = discover(args.agent_file, args.target_org)
    else:
        if not args.agent_dir.exists():
            print(f"Error: {args.agent_dir} not found", file=sys.stderr)
            sys.exit(1)
        report = discover_dir(args.agent_dir, args.target_org)

    print_report(report)

    # Exit with non-zero if any targets are missing
    sys.exit(0 if report.all_found else 1)


if __name__ == "__main__":
    main()
