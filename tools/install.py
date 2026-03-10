#!/usr/bin/env python3
"""
agentforce-adlc Installer for Claude Code

Usage:
    curl -sSL https://raw.githubusercontent.com/Authoring-Agent/agentforce-adlc/main/tools/install.py | python3

    # Or with options:
    python3 install.py                # Install
    python3 install.py --update       # Check for updates and apply if available
    python3 install.py --force-update # Force reinstall even if up-to-date
    python3 install.py --uninstall    # Remove agentforce-adlc
    python3 install.py --status       # Show installation status
    python3 install.py --dry-run      # Preview changes without writing
    python3 install.py --force        # Skip confirmations

Requirements:
    - Python 3.10+ (standard library only)
    - Claude Code installed (~/.claude/ directory exists)
"""

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

INSTALLER_VERSION = "0.1.0"

# GitHub repository
GITHUB_OWNER = "Authoring-Agent"
GITHUB_REPO = "agentforce-adlc"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main"

# Installation paths
CLAUDE_DIR = Path.home() / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"
HOOKS_DIR = CLAUDE_DIR / "hooks"
HOOKS_SCRIPTS_DIR = HOOKS_DIR / "scripts"
INSTALL_DIR = CLAUDE_DIR / "adlc"
META_FILE = CLAUDE_DIR / ".adlc.json"
INSTALLER_DEST = CLAUDE_DIR / "adlc-install.py"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"

# Prefixes (only manage our own files, never touch sf-* or agentforce-md-*)
SKILL_PREFIX = "adlc-"

# Skills to install (relative to repo root)
SKILL_DIRS = [
    "skills/adlc-author",
    "skills/adlc-discover",
    "skills/adlc-scaffold",
    "skills/adlc-deploy",
    "skills/adlc-run",
    "skills/adlc-test",
    "skills/adlc-optimize",
]

# Agent definitions to install
AGENT_FILES = [
    "agents/adlc-orchestrator.md",
    "agents/adlc-author.md",
    "agents/adlc-engineer.md",
    "agents/adlc-qa.md",
]

# Hook scripts to install
HOOK_SCRIPTS = [
    "shared/hooks/scripts/guardrails.py",
    "shared/hooks/scripts/agent-validator.py",
    "shared/hooks/scripts/session-init.py",
    "shared/hooks/scripts/stdin_utils.py",
]

HOOK_REGISTRY = "shared/hooks/skills-registry.json"


# ============================================================================
# OUTPUT HELPERS
# ============================================================================

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


def print_step(msg: str):
    print(f"\n{c('▸', Colors.BLUE)} {c(msg, Colors.BOLD)}")


def print_substep(msg: str):
    print(f"  {c('✓', Colors.GREEN)} {msg}")


def print_info(msg: str):
    print(f"  {c('ℹ', Colors.BLUE)} {msg}")


def print_warn(msg: str):
    print(f"  {c('⚠', Colors.YELLOW)} {msg}")


def print_error(msg: str):
    print(f"  {c('✗', Colors.RED)} {msg}")


# ============================================================================
# FILESYSTEM HELPERS
# ============================================================================

def safe_rmtree(path: Path):
    """Remove a directory tree, handling symlinks safely."""
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _find_python3() -> str:
    """Find the python3 executable path reliably.

    sys.executable can be empty or wrong when piped via curl | python3.
    Falls back to searching PATH.
    """
    exe = sys.executable
    if exe and os.path.isfile(exe):
        return exe

    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, "python3")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return "python3"


# ============================================================================
# SSL HELPERS
# ============================================================================

_SSL_CONTEXT_CACHE: Optional[ssl.SSLContext] = None
_SSL_ERROR_SHOWN = False


def _build_ssl_context() -> ssl.SSLContext:
    """Build best available SSL context for urllib."""
    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file and os.path.isfile(cert_file):
        return ssl.create_default_context(cafile=cert_file)

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    return ssl.create_default_context()


def _get_ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT_CACHE
    if _SSL_CONTEXT_CACHE is None:
        _SSL_CONTEXT_CACHE = _build_ssl_context()
    return _SSL_CONTEXT_CACHE


def _handle_ssl_error(e: Exception) -> bool:
    global _SSL_ERROR_SHOWN
    is_ssl = False
    if isinstance(e, urllib.error.URLError) and hasattr(e, "reason"):
        if isinstance(e.reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
            is_ssl = True
    elif isinstance(e, (ssl.SSLCertVerificationError, ssl.SSLError)):
        is_ssl = True

    if is_ssl and not _SSL_ERROR_SHOWN:
        _SSL_ERROR_SHOWN = True
        print()
        print_error("SSL certificate verification failed")
        print_info("This is common with python.org installs on macOS.")
        print()
        print(c("  Fix options (try in order):", Colors.BOLD))
        print()
        print("  1. Run the macOS certificate installer:")
        print("     /Applications/Python\\ 3.*/Install\\ Certificates.command")
        print()
        print("  2. Install certifi and set SSL_CERT_FILE:")
        print("     pip3 install certifi")
        print('     export SSL_CERT_FILE="$(python3 -c \'import certifi; print(certifi.where())\')"')
        print()

    return is_ssl


# ============================================================================
# METADATA
# ============================================================================

def write_metadata(version: str, skills: List[str], agents: List[str],
                   hooks: List[str], commit_sha: Optional[str] = None):
    """Write install metadata to ~/.claude/.adlc.json."""
    META_FILE.write_text(json.dumps({
        "method": "unified",
        "version": version,
        "commit_sha": commit_sha,
        "installed_at": datetime.now().isoformat(),
        "installer_version": INSTALLER_VERSION,
        "install_dir": str(INSTALL_DIR),
        "skills": skills,
        "agents": agents,
        "hooks": hooks,
    }, indent=2) + "\n")


def read_metadata() -> Optional[Dict[str, Any]]:
    """Read install metadata."""
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            return None
    return None


# ============================================================================
# DOWNLOAD & VERSION
# ============================================================================

def download_repo_zip(target_dir: Path, ref: str = "main") -> bool:
    """Download repo zip from GitHub and extract to target_dir."""
    zip_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{ref}.zip"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            print_info(f"Downloading from {zip_url}...")
            with urllib.request.urlopen(zip_url, timeout=60, context=_get_ssl_context()) as resp:
                tmp_file.write(resp.read())

        with zipfile.ZipFile(tmp_path, "r") as zf:
            top_dirs = {name.split("/")[0] for name in zf.namelist() if "/" in name}
            if len(top_dirs) != 1:
                print_error("Unexpected zip structure")
                return False
            top_dir = top_dirs.pop()

            with tempfile.TemporaryDirectory() as extract_tmp:
                zf.extractall(extract_tmp)
                extracted = Path(extract_tmp) / top_dir

                safe_rmtree(target_dir)
                shutil.copytree(extracted, target_dir)

        return True

    except (urllib.error.URLError, zipfile.BadZipFile, IOError) as e:
        if not _handle_ssl_error(e):
            print_error(f"Download failed: {e}")
        return False
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def fetch_remote_version(ref: str = "main") -> Optional[str]:
    """Fetch the VERSION file from the remote repo."""
    url = f"{GITHUB_RAW_URL}/VERSION"
    try:
        with urllib.request.urlopen(url, timeout=15, context=_get_ssl_context()) as resp:
            return resp.read().decode().strip()
    except (urllib.error.URLError, IOError) as e:
        if not _handle_ssl_error(e):
            print_error(f"Failed to check remote version: {e}")
        return None


def fetch_remote_commit_sha(ref: str = "main") -> Optional[str]:
    """Fetch the latest commit SHA from the GitHub API."""
    url = f"{GITHUB_API_URL}/commits/{ref}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=15, context=_get_ssl_context()) as resp:
            data = json.loads(resp.read().decode())
            return data.get("sha", "")[:12]
    except (urllib.error.URLError, IOError, json.JSONDecodeError, KeyError):
        return None


def get_local_commit_sha(repo_root: Path) -> Optional[str]:
    """Get the current commit SHA from a local git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


# ============================================================================
# SKILL INSTALLATION
# ============================================================================

def install_skills(source_dir: Path, dry_run: bool = False) -> List[str]:
    """Copy skills from source to ~/.claude/skills/adlc-*/."""
    installed = []
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for skill_rel in SKILL_DIRS:
        src = source_dir / skill_rel
        skill_name = Path(skill_rel).name

        if not src.exists():
            print_warn(f"Skill not found: {skill_rel}")
            continue

        target = SKILLS_DIR / skill_name
        if dry_run:
            print_info(f"Would install skill: {skill_name}")
        else:
            safe_rmtree(target)
            shutil.copytree(src, target)
            print_substep(f"Skill: {skill_name}")

        installed.append(skill_name)

    return installed


def install_agents(source_dir: Path, dry_run: bool = False) -> List[str]:
    """Copy agent definitions from source to ~/.claude/agents/."""
    installed = []
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    for agent_rel in AGENT_FILES:
        src = source_dir / agent_rel
        if not src.exists():
            print_warn(f"Agent not found: {agent_rel}")
            continue

        target = AGENTS_DIR / src.name
        if dry_run:
            print_info(f"Would install agent: {src.name}")
        else:
            shutil.copy2(src, target)
            print_substep(f"Agent: {src.name}")

        installed.append(src.name)

    return installed


def install_hooks(source_dir: Path, dry_run: bool = False) -> List[str]:
    """Copy hook scripts from source to ~/.claude/hooks/scripts/."""
    installed = []
    HOOKS_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    for hook_rel in HOOK_SCRIPTS:
        src = source_dir / hook_rel
        if not src.exists():
            print_warn(f"Hook not found: {hook_rel}")
            continue

        # Prefix hook scripts with adlc- to avoid conflicts (except stdin_utils)
        dest_name = src.name
        if not dest_name.startswith("adlc-") and not dest_name.startswith("stdin_"):
            dest_name = f"adlc-{dest_name}"

        target = HOOKS_SCRIPTS_DIR / dest_name
        if dry_run:
            print_info(f"Would install hook: {dest_name}")
        else:
            shutil.copy2(src, target)
            print_substep(f"Hook: {dest_name}")

        installed.append(dest_name)

    # Copy skills registry
    registry_src = source_dir / HOOK_REGISTRY
    if registry_src.exists():
        registry_dest = HOOKS_DIR / "skills-registry.json"
        if dry_run:
            print_info("Would install skills-registry.json")
        else:
            shutil.copy2(registry_src, registry_dest)
            print_substep("Hook: skills-registry.json")
        installed.append("skills-registry.json")

    return installed


def prune_orphan_skills(current_skills: List[str], dry_run: bool = False) -> int:
    """Remove adlc-* skills that are no longer in the repo."""
    pruned = 0
    if not SKILLS_DIR.exists():
        return pruned

    current_set = set(current_skills)
    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and item.name.startswith(SKILL_PREFIX) and item.name not in current_set:
            if dry_run:
                print_info(f"Would remove orphan skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed orphan skill: {item.name}")
            pruned += 1

    return pruned


# ============================================================================
# HOOK CONFIGURATION IN settings.json
# ============================================================================

def _find_adlc_hook_index(hooks_list: list, marker: str) -> int:
    """Find the index of an existing ADLC hook entry by checking command strings."""
    for i, entry in enumerate(hooks_list):
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if marker in cmd:
                return i
    return -1


def configure_hooks(dry_run: bool = False) -> bool:
    """Merge ADLC hook config into ~/.claude/settings.json."""
    guardrail_cmd = f"python3 {HOOKS_SCRIPTS_DIR / 'adlc-guardrails.py'}"
    validator_cmd = f"python3 {HOOKS_SCRIPTS_DIR / 'adlc-agent-validator.py'}"

    adlc_pre_hook = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": guardrail_cmd, "timeout": 5000}],
    }
    adlc_post_hook = {
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": validator_cmd, "timeout": 10000}],
    }

    if dry_run:
        print_info("Would configure hooks in settings.json")
        return True

    # Read existing settings
    settings: Dict[str, Any] = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # Configure PreToolUse
    pre_hooks = hooks.setdefault("PreToolUse", [])
    idx = _find_adlc_hook_index(pre_hooks, "adlc-guardrails")
    if idx >= 0:
        pre_hooks[idx] = adlc_pre_hook
    else:
        pre_hooks.append(adlc_pre_hook)

    # Configure PostToolUse
    post_hooks = hooks.setdefault("PostToolUse", [])
    idx = _find_adlc_hook_index(post_hooks, "adlc-agent-validator")
    if idx >= 0:
        post_hooks[idx] = adlc_post_hook
    else:
        post_hooks.append(adlc_post_hook)

    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")
    return True


def remove_hooks_from_settings(dry_run: bool = False) -> bool:
    """Remove ADLC hooks from ~/.claude/settings.json."""
    if not SETTINGS_FILE.exists():
        return True

    if dry_run:
        print_info("Would remove ADLC hooks from settings.json")
        return True

    try:
        settings = json.loads(SETTINGS_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return True

    hooks = settings.get("hooks", {})
    changed = False

    for key in ("PreToolUse", "PostToolUse"):
        hook_list = hooks.get(key, [])
        filtered = [
            entry for entry in hook_list
            if not any("adlc-" in h.get("command", "") for h in entry.get("hooks", []))
        ]
        if len(filtered) != len(hook_list):
            hooks[key] = filtered
            changed = True

    # Clean up empty lists/dicts
    for key in list(hooks.keys()):
        if not hooks[key]:
            del hooks[key]
    if not hooks and "hooks" in settings:
        del settings["hooks"]

    if changed:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")

    return True


# ============================================================================
# VALIDATION
# ============================================================================

def validate_installation() -> List[str]:
    """Validate that installation completed correctly. Returns list of issues."""
    issues = []

    # Check install dir
    if not INSTALL_DIR.exists():
        issues.append(f"Install directory missing: {INSTALL_DIR}")
        return issues

    # Check skills
    if SKILLS_DIR.exists():
        for skill_rel in SKILL_DIRS:
            skill_name = Path(skill_rel).name
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            if not skill_md.exists():
                issues.append(f"SKILL.md missing: {skill_name}")
    else:
        issues.append(f"Skills directory missing: {SKILLS_DIR}")

    # Check agents
    for agent_rel in AGENT_FILES:
        agent_name = Path(agent_rel).name
        if not (AGENTS_DIR / agent_name).exists():
            issues.append(f"Agent missing: {agent_name}")

    # Check hooks
    for hook_rel in HOOK_SCRIPTS:
        hook_name = Path(hook_rel).name
        dest_name = hook_name
        if not dest_name.startswith("adlc-") and not dest_name.startswith("stdin_"):
            dest_name = f"adlc-{dest_name}"
        if not (HOOKS_SCRIPTS_DIR / dest_name).exists():
            issues.append(f"Hook missing: {dest_name}")

    # Check hooks in settings.json
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
            hooks = settings.get("hooks", {})
            pre = hooks.get("PreToolUse", [])
            post = hooks.get("PostToolUse", [])
            has_guardrail = any(
                "adlc-guardrails" in h.get("command", "")
                for entry in pre for h in entry.get("hooks", [])
            )
            has_validator = any(
                "adlc-agent-validator" in h.get("command", "")
                for entry in post for h in entry.get("hooks", [])
            )
            if not has_guardrail:
                issues.append("Guardrail hook not configured in settings.json")
            if not has_validator:
                issues.append("Validator hook not configured in settings.json")
        except (json.JSONDecodeError, IOError):
            issues.append("Could not read settings.json for hook validation")

    # Check metadata
    if not META_FILE.exists():
        issues.append(f"Metadata file missing: {META_FILE}")

    return issues


# ============================================================================
# REMOVE HELPERS
# ============================================================================

def remove_skills(dry_run: bool = False) -> int:
    """Remove all installed adlc-* skills from ~/.claude/skills/."""
    removed = 0
    if not SKILLS_DIR.exists():
        return removed

    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and item.name.startswith(SKILL_PREFIX):
            if dry_run:
                print_info(f"Would remove skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed skill: {item.name}")
            removed += 1

    return removed


def remove_agents(dry_run: bool = False) -> int:
    """Remove all installed adlc-* agents from ~/.claude/agents/."""
    removed = 0
    if not AGENTS_DIR.exists():
        return removed

    for item in sorted(AGENTS_DIR.iterdir()):
        if item.is_file() and item.name.startswith(SKILL_PREFIX) and item.suffix == ".md":
            if dry_run:
                print_info(f"Would remove agent: {item.name}")
            else:
                item.unlink()
                print_substep(f"Removed agent: {item.name}")
            removed += 1

    return removed


def remove_hooks(dry_run: bool = False) -> int:
    """Remove ADLC hook scripts from ~/.claude/hooks/."""
    removed = 0

    # Remove scripts
    if HOOKS_SCRIPTS_DIR.exists():
        for item in sorted(HOOKS_SCRIPTS_DIR.iterdir()):
            if item.is_file() and item.name.startswith("adlc-"):
                if dry_run:
                    print_info(f"Would remove hook: {item.name}")
                else:
                    item.unlink()
                    print_substep(f"Removed hook: {item.name}")
                removed += 1

        # Remove stdin_utils.py (shared helper)
        stdin_utils = HOOKS_SCRIPTS_DIR / "stdin_utils.py"
        if stdin_utils.exists():
            if dry_run:
                print_info("Would remove hook: stdin_utils.py")
            else:
                stdin_utils.unlink()
                print_substep("Removed hook: stdin_utils.py")
            removed += 1

    # Remove registry
    registry = HOOKS_DIR / "skills-registry.json"
    if registry.exists():
        if dry_run:
            print_info("Would remove skills-registry.json")
        else:
            registry.unlink()
            print_substep("Removed: skills-registry.json")
        removed += 1

    return removed


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_install(dry_run: bool = False, force: bool = False,
                called_from_bash: bool = False) -> int:
    """Install agentforce-adlc to ~/.claude/."""
    if not called_from_bash:
        print(f"\n{c('agentforce-adlc installer', Colors.BOLD)}")

    # Check prerequisites
    if not CLAUDE_DIR.exists():
        print_error(f"Claude Code directory not found: {CLAUDE_DIR}")
        print_info("Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code")
        return 1

    # Check existing installation
    meta = read_metadata()
    if meta and not force:
        version = meta.get("version", "unknown")
        print_info(f"agentforce-adlc v{version} is already installed.")
        print_info("Use --force to reinstall, or --update to check for updates.")
        return 0

    # Detect local clone vs remote install
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    local_version_file = repo_root / "VERSION"
    commit_sha = None

    if local_version_file.exists():
        # Installing from local clone
        print_step("Installing from local clone")
        version = local_version_file.read_text().strip()
        commit_sha = get_local_commit_sha(repo_root)
        source_dir = repo_root

        if dry_run:
            print_info(f"Would install v{version} from {repo_root}")
            print_info(f"Would copy repo to {INSTALL_DIR}")
            install_skills(source_dir, dry_run=True)
            install_agents(source_dir, dry_run=True)
            install_hooks(source_dir, dry_run=True)
            configure_hooks(dry_run=True)
            print_info(f"Would copy installer to {INSTALLER_DEST}")
            print_info(f"Would write metadata to {META_FILE}")
            print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
            return 0

        print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))

        # Copy repo to install dir
        print_step("Copying repo to install directory")
        safe_rmtree(INSTALL_DIR)
        shutil.copytree(repo_root, INSTALL_DIR, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", ".venv", "force-app",
        ))
        print_substep(f"Copied to {INSTALL_DIR}")

    else:
        # Remote install (curl | python3)
        print_step("Downloading agentforce-adlc")
        version_str = fetch_remote_version()
        if not version_str:
            print_error("Could not determine remote version")
            return 1
        version = version_str
        commit_sha = fetch_remote_commit_sha()
        source_dir = INSTALL_DIR  # Will be populated by download

        if dry_run:
            print_info(f"Would install v{version} from GitHub")
            print_info(f"Would download repo to {INSTALL_DIR}")
            print_info(f"Would install skills to {SKILLS_DIR}")
            print_info(f"Would install agents to {AGENTS_DIR}")
            print_info(f"Would install hooks to {HOOKS_SCRIPTS_DIR}")
            print_info("Would configure hooks in settings.json")
            print_info(f"Would copy installer to {INSTALLER_DEST}")
            print_info(f"Would write metadata to {META_FILE}")
            print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
            return 0

        print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))

        if not download_repo_zip(INSTALL_DIR):
            return 1
        print_substep(f"Extracted to {INSTALL_DIR}")

    # Install skills
    print_step("Installing skills")
    skills = install_skills(source_dir)
    if skills:
        print_substep(f"{len(skills)} skill(s) installed")
    else:
        print_warn("No skills found to install")

    pruned = prune_orphan_skills(skills)
    if pruned:
        print_substep(f"{pruned} orphan skill(s) removed")

    # Install agents
    print_step("Installing agents")
    agents = install_agents(source_dir)
    if agents:
        print_substep(f"{len(agents)} agent(s) installed")

    # Install hooks
    print_step("Installing hooks")
    hooks = install_hooks(source_dir)
    if hooks:
        print_substep(f"{len(hooks)} hook(s) installed")

    # Auto-configure hooks in settings.json
    print_step("Configuring hooks in settings.json")
    if configure_hooks():
        print_substep("Hooks configured in settings.json")
    else:
        print_warn("Could not configure hooks in settings.json")

    # Copy installer for self-update
    print_step("Setting up self-updater")
    installer_src = INSTALL_DIR / "tools" / "install.py"
    if installer_src.exists():
        shutil.copy2(installer_src, INSTALLER_DEST)
        print_substep(f"Installer copied to {INSTALLER_DEST}")
    else:
        print_warn("Installer source not found; self-update won't work")

    # Write metadata
    write_metadata(version, skills, agents, hooks, commit_sha=commit_sha)
    print_substep(f"Metadata written to {META_FILE}")

    # Post-install validation
    print_step("Validating installation")
    issues = validate_installation()
    if issues:
        for issue in issues:
            print_warn(issue)
        print_warn("Installation completed with warnings")
    else:
        print_substep("All checks passed")

    # Summary
    print(f"\n{c('Installation complete!', Colors.GREEN)}")
    print()
    print(f"  Version:  {version}" + (f" ({commit_sha})" if commit_sha else ""))
    print(f"  Skills:   {', '.join(skills) if skills else 'none'}")
    print(f"  Agents:   {', '.join(agents) if agents else 'none'}")
    print(f"  Hooks:    {len(hooks)} script(s) + settings.json configured")
    print()
    print(f"  Update:   python3 {INSTALLER_DEST} --update")
    print(f"  Status:   python3 {INSTALLER_DEST} --status")
    print(f"  Remove:   python3 {INSTALLER_DEST} --uninstall")
    print()
    print_info("Restart Claude Code for skills to take effect.")
    print()

    return 0


def cmd_update(dry_run: bool = False, force_update: bool = False) -> int:
    """Check for updates and apply if available."""
    print(f"\n{c('agentforce-adlc updater', Colors.BOLD)}")

    meta = read_metadata()
    if not meta:
        print_info("agentforce-adlc is not installed. Running install...")
        return cmd_install(dry_run=dry_run)

    local_version = meta.get("version", "unknown")
    local_sha = meta.get("commit_sha")
    print_info(f"Installed version: {local_version}" + (f" ({local_sha})" if local_sha else ""))

    # Fetch remote version + commit SHA
    print_step("Checking for updates")
    remote_version = fetch_remote_version()
    if not remote_version:
        print_error("Could not check remote version")
        return 1

    remote_sha = fetch_remote_commit_sha()
    print_info(f"Remote version: {remote_version}" + (f" ({remote_sha})" if remote_sha else ""))

    # Detect changes
    version_changed = remote_version != local_version
    content_changed = (
        remote_sha and local_sha
        and remote_sha != local_sha
        and not version_changed
    )

    if not version_changed and not content_changed and not force_update:
        print(f"\n{c('Already up to date.', Colors.GREEN)}")
        return 0

    if force_update:
        print_info("Force update requested")
    elif version_changed:
        print_info(f"Version update available: {local_version} -> {remote_version}")
    elif content_changed:
        print_info(f"Content update available: {local_sha} -> {remote_sha}")

    return cmd_install(dry_run=dry_run, force=True)


def cmd_uninstall(dry_run: bool = False, force: bool = False) -> int:
    """Remove agentforce-adlc installation."""
    print(f"\n{c('agentforce-adlc uninstaller', Colors.BOLD)}")

    meta = read_metadata()
    if not meta and not INSTALL_DIR.exists():
        print_info("agentforce-adlc is not installed.")
        return 0

    if not force:
        print()
        print("  This will remove:")
        print(f"    - {INSTALL_DIR}")
        print(f"    - {SKILLS_DIR}/adlc-* skills")
        print(f"    - {AGENTS_DIR}/adlc-* agents")
        print(f"    - Hook scripts + settings.json entries")
        print(f"    - {META_FILE}")
        print(f"    - {INSTALLER_DEST}")
        print()
        try:
            answer = input("  Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if answer not in ("y", "yes"):
            print_info("Cancelled.")
            return 0

    # Remove install dir
    if INSTALL_DIR.exists():
        if dry_run:
            print_info(f"Would remove {INSTALL_DIR}")
        else:
            safe_rmtree(INSTALL_DIR)
            print_substep(f"Removed {INSTALL_DIR}")

    # Remove skills
    removed_skills = remove_skills(dry_run=dry_run)
    if removed_skills:
        print_substep(f"Removed {removed_skills} skill(s)")

    # Remove agents
    removed_agents = remove_agents(dry_run=dry_run)
    if removed_agents:
        print_substep(f"Removed {removed_agents} agent(s)")

    # Remove hooks
    removed_hooks = remove_hooks(dry_run=dry_run)
    if removed_hooks:
        print_substep(f"Removed {removed_hooks} hook(s)")

    # Remove hooks from settings.json
    remove_hooks_from_settings(dry_run=dry_run)
    if not dry_run:
        print_substep("Removed ADLC hooks from settings.json")

    # Remove metadata
    if META_FILE.exists():
        if dry_run:
            print_info(f"Would remove {META_FILE}")
        else:
            META_FILE.unlink()
            print_substep(f"Removed {META_FILE}")

    # Remove self-updater (but not if we're running from it)
    if INSTALLER_DEST.exists():
        running_from_dest = Path(__file__).resolve() == INSTALLER_DEST.resolve()
        if dry_run:
            print_info(f"Would remove {INSTALLER_DEST}")
        elif not running_from_dest:
            INSTALLER_DEST.unlink()
            print_substep(f"Removed {INSTALLER_DEST}")
        else:
            print_info(f"Skipping removal of running installer: {INSTALLER_DEST}")
            print_info("You can delete it manually.")

    if dry_run:
        print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
    else:
        print(f"\n{c('Uninstall complete.', Colors.GREEN)}")

    return 0


def cmd_status() -> int:
    """Show installation status."""
    print(f"\n{c('agentforce-adlc status', Colors.BOLD)}")

    meta = read_metadata()
    if not meta:
        print_info("agentforce-adlc is not installed.")
        return 1

    commit_sha = meta.get("commit_sha")
    print()
    print(f"  Version:      {meta.get('version', 'unknown')}" +
          (f" ({commit_sha})" if commit_sha else ""))
    print(f"  Installed at: {meta.get('installed_at', 'unknown')}")
    print(f"  Install dir:  {INSTALL_DIR}")
    print(f"  Metadata:     {META_FILE}")

    # List installed skills
    print()
    print(f"  {c('Skills:', Colors.BOLD)}")
    if SKILLS_DIR.exists():
        found = False
        for item in sorted(SKILLS_DIR.iterdir()):
            if item.is_dir() and item.name.startswith(SKILL_PREFIX):
                skill_md = item / "SKILL.md"
                status = "ok" if skill_md.exists() else "MISSING SKILL.md"
                print(f"    - {item.name} ({status})")
                found = True
        if not found:
            print("    (none)")
    else:
        print("    (skills directory not found)")

    # List installed agents
    print()
    print(f"  {c('Agents:', Colors.BOLD)}")
    if AGENTS_DIR.exists():
        found = False
        for item in sorted(AGENTS_DIR.iterdir()):
            if item.is_file() and item.name.startswith(SKILL_PREFIX) and item.suffix == ".md":
                print(f"    - {item.name}")
                found = True
        if not found:
            print("    (none)")
    else:
        print("    (agents directory not found)")

    # List hooks
    print()
    print(f"  {c('Hooks:', Colors.BOLD)}")
    if HOOKS_SCRIPTS_DIR.exists():
        found = False
        for item in sorted(HOOKS_SCRIPTS_DIR.iterdir()):
            if item.is_file() and item.name.startswith("adlc-"):
                print(f"    - {item.name}")
                found = True
        if not found:
            print("    (none)")
    else:
        print("    (hooks directory not found)")

    # Check settings.json hooks
    print()
    print(f"  {c('Hook configuration:', Colors.BOLD)}")
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
            hooks = settings.get("hooks", {})
            pre = hooks.get("PreToolUse", [])
            post = hooks.get("PostToolUse", [])
            has_guardrail = any(
                "adlc-guardrails" in h.get("command", "")
                for entry in pre for h in entry.get("hooks", [])
            )
            has_validator = any(
                "adlc-agent-validator" in h.get("command", "")
                for entry in post for h in entry.get("hooks", [])
            )
            print(f"    PreToolUse (guardrails):  {'configured' if has_guardrail else 'NOT configured'}")
            print(f"    PostToolUse (validator):  {'configured' if has_validator else 'NOT configured'}")
        except (json.JSONDecodeError, IOError):
            print("    Could not read settings.json")
    else:
        print("    settings.json not found")

    # Check for coexistence
    sf_meta = CLAUDE_DIR / ".sf-skills.json"
    md_meta = CLAUDE_DIR / ".agentforce-md.json"
    coexist = []
    if sf_meta.exists():
        coexist.append("sf-skills")
    if md_meta.exists():
        coexist.append("agentforce-md")
    if coexist:
        print()
        print_info(f"Also installed: {', '.join(coexist)} (no conflicts expected)")

    print()
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="agentforce-adlc installer for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--update", action="store_true",
                        help="Check for updates and apply if available")
    parser.add_argument("--force-update", action="store_true",
                        help="Force reinstall even if up-to-date")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove agentforce-adlc")
    parser.add_argument("--status", action="store_true",
                        help="Show installation status")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmations")
    parser.add_argument("--called-from-bash", action="store_true",
                        help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.status:
        sys.exit(cmd_status())
    elif args.uninstall:
        sys.exit(cmd_uninstall(dry_run=args.dry_run, force=args.force))
    elif args.update or args.force_update:
        sys.exit(cmd_update(dry_run=args.dry_run, force_update=args.force_update))
    else:
        sys.exit(cmd_install(dry_run=args.dry_run, force=args.force,
                             called_from_bash=args.called_from_bash))


if __name__ == "__main__":
    main()
