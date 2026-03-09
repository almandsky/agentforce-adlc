#!/usr/bin/env python3
"""Install agentforce-adlc skills, agents, and hooks to ~/.claude/.

Copies skills, agents, and hook scripts to the global Claude Code configuration
directory. Coexists with sf-skills and agentforce-md installations.

Usage:
    python3 tools/install.py              # Install
    python3 tools/install.py --status     # Check installation status
    python3 tools/install.py --uninstall  # Remove installed files
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Installation configuration
VERSION = "0.1.0"
PREFIX = "adlc-"
CLAUDE_DIR = Path.home() / ".claude"
METADATA_FILE = CLAUDE_DIR / ".adlc-skills.json"

# Source directories (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent

SKILL_DIRS = [
    "skills/adlc-author",
    "skills/adlc-discover",
    "skills/adlc-scaffold",
    "skills/adlc-deploy",
    "skills/adlc-run",
    "skills/adlc-test",
    "skills/adlc-optimize",
]

AGENT_FILES = [
    "agents/adlc-orchestrator.md",
    "agents/adlc-author.md",
    "agents/adlc-engineer.md",
    "agents/adlc-qa.md",
]

HOOK_SCRIPTS = [
    "shared/hooks/scripts/guardrails.py",
    "shared/hooks/scripts/agent-validator.py",
    "shared/hooks/scripts/session-init.py",
    "shared/hooks/scripts/stdin_utils.py",
    "shared/hooks/skills-registry.json",
]


def install():
    """Install skills, agents, and hooks to ~/.claude/."""
    print(f"\nInstalling agentforce-adlc v{VERSION}...")
    print(f"Target: {CLAUDE_DIR}\n")

    installed_files = []

    # Install skills
    skills_dir = CLAUDE_DIR / "skills"
    for skill_src in SKILL_DIRS:
        src = PROJECT_ROOT / skill_src
        if not src.exists():
            print(f"  SKIP: {skill_src} (not found)")
            continue

        skill_name = src.name
        dest = skills_dir / skill_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        installed_files.append(str(dest))
        print(f"  Skill: {skill_name}")

    # Install agents
    agents_dir = CLAUDE_DIR / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for agent_src in AGENT_FILES:
        src = PROJECT_ROOT / agent_src
        if not src.exists():
            print(f"  SKIP: {agent_src} (not found)")
            continue

        dest = agents_dir / src.name
        shutil.copy2(src, dest)
        installed_files.append(str(dest))
        print(f"  Agent: {src.name}")

    # Install hooks
    hooks_dir = CLAUDE_DIR / "hooks" / "scripts"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_src in HOOK_SCRIPTS:
        src = PROJECT_ROOT / hook_src
        if not src.exists():
            print(f"  SKIP: {hook_src} (not found)")
            continue

        # Prefix hook scripts with adlc- to avoid conflicts
        dest_name = src.name
        if not dest_name.startswith("adlc-") and not dest_name.startswith("stdin_") and not dest_name.endswith(".json"):
            dest_name = f"adlc-{dest_name}"

        if src.name.endswith(".json"):
            dest = CLAUDE_DIR / "hooks" / dest_name
        else:
            dest = hooks_dir / dest_name
        shutil.copy2(src, dest)
        installed_files.append(str(dest))
        print(f"  Hook: {dest_name}")

    # Save metadata
    metadata = {
        "version": VERSION,
        "installed_at": datetime.now().isoformat(),
        "source": str(PROJECT_ROOT),
        "files": installed_files,
    }
    METADATA_FILE.write_text(json.dumps(metadata, indent=2))

    print(f"\n✅ Installed {len(installed_files)} file(s)")
    print(f"   Metadata: {METADATA_FILE}")

    # Print hook configuration instructions
    print(f"\nTo enable hooks, add to your project's .claude/settings.json:")
    print(json.dumps({
        "hooks": {
            "PreToolUse": [{
                "matcher": "Bash",
                "hooks": [{
                    "type": "command",
                    "command": f"python3 {hooks_dir / 'adlc-guardrails.py'}",
                    "timeout": 5000,
                }],
            }],
            "PostToolUse": [{
                "matcher": "Write|Edit",
                "hooks": [{
                    "type": "command",
                    "command": f"python3 {hooks_dir / 'adlc-agent-validator.py'}",
                    "timeout": 10000,
                }],
            }],
        }
    }, indent=2))
    print()


def status():
    """Show installation status."""
    if not METADATA_FILE.exists():
        print("agentforce-adlc: Not installed")
        return

    metadata = json.loads(METADATA_FILE.read_text())
    print(f"\nagentforce-adlc v{metadata.get('version', '?')}")
    print(f"Installed: {metadata.get('installed_at', '?')}")
    print(f"Source: {metadata.get('source', '?')}")

    files = metadata.get("files", [])
    existing = sum(1 for f in files if Path(f).exists())
    print(f"Files: {existing}/{len(files)} present")

    if existing < len(files):
        print("\nMissing files:")
        for f in files:
            if not Path(f).exists():
                print(f"  ❌ {f}")
    print()


def uninstall():
    """Remove installed files."""
    if not METADATA_FILE.exists():
        print("agentforce-adlc: Not installed")
        return

    metadata = json.loads(METADATA_FILE.read_text())
    files = metadata.get("files", [])

    removed = 0
    for f in files:
        p = Path(f)
        if p.is_dir():
            shutil.rmtree(p)
            removed += 1
        elif p.exists():
            p.unlink()
            removed += 1

    METADATA_FILE.unlink()
    print(f"\n✅ Removed {removed} file(s)")
    print()


def main():
    parser = argparse.ArgumentParser(description="Install agentforce-adlc to ~/.claude/")
    parser.add_argument("--status", action="store_true", help="Show installation status")
    parser.add_argument("--uninstall", action="store_true", help="Remove installed files")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.uninstall:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
