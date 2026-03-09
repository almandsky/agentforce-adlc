#!/usr/bin/env python3
"""SessionStart hook: preflight checks for agentforce-adlc.

Checks:
1. sf CLI is installed and accessible
2. Connected org exists (default or specified)
3. sfdx-project.json exists in current directory
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from stdin_utils import read_stdin_safe
except ImportError:
    def read_stdin_safe(timeout_seconds=0.1):
        if sys.stdin.isatty():
            return {}
        try:
            return json.load(sys.stdin)
        except Exception:
            return {}


def check_sf_cli() -> tuple[bool, str]:
    """Check if sf CLI is installed."""
    if not shutil.which("sf"):
        return False, "sf CLI not found. Install: https://developer.salesforce.com/tools/salesforcecli"
    try:
        result = subprocess.run(["sf", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return True, f"sf CLI: {version}"
    except Exception:
        pass
    return False, "sf CLI found but version check failed"


def check_connected_org() -> tuple[bool, str]:
    """Check if there's a default connected org."""
    try:
        result = subprocess.run(
            ["sf", "org", "display", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            username = data.get("result", {}).get("username", "unknown")
            return True, f"Connected org: {username}"
    except Exception:
        pass
    return False, "No default org connected. Run: sf org login web"


def check_project_json() -> tuple[bool, str]:
    """Check if sfdx-project.json exists."""
    if Path("sfdx-project.json").exists():
        return True, "sfdx-project.json found"
    return False, "sfdx-project.json not found in current directory"


def main():
    """Run preflight checks and report status."""
    checks = [
        ("SF CLI", check_sf_cli()),
        ("Org Connection", check_connected_org()),
        ("Project Config", check_project_json()),
    ]

    messages = []
    all_ok = True
    for name, (ok, msg) in checks:
        status = "OK" if ok else "MISSING"
        messages.append(f"  [{status}] {name}: {msg}")
        if not ok:
            all_ok = False

    context = "ADLC Preflight Checks:\n" + "\n".join(messages)
    if not all_ok:
        context += "\n\n  Some checks failed. Skills may not work correctly."

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
