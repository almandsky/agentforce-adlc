"""Load the ADLC agent definitions (agents/*.md) as SDK AgentDefinition objects.

The repo ships agent markdown files with YAML frontmatter (name, description,
tools, skills) followed by a prompt body. This module parses them into the
form the Claude Agent SDK expects so the authoring agent can delegate to them
via the Task tool.
"""

import re
from pathlib import Path

from claude_agent_sdk import AgentDefinition

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_agent_md(path: Path) -> tuple[str, AgentDefinition]:
    """Parse one agent .md file into (name, AgentDefinition)."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path}: missing YAML frontmatter")

    frontmatter_raw, body = match.groups()
    meta: dict[str, str] = {}
    for line in frontmatter_raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()

    name = meta.get("name", path.stem)
    description = meta.get("description", "")
    tools = [t.strip() for t in meta.get("tools", "").split(",") if t.strip()]

    return name, AgentDefinition(
        description=description,
        prompt=body.strip(),
        tools=tools or None,
    )


def load_adlc_agents(agents_dir: Path) -> dict[str, AgentDefinition]:
    """Load all adlc-*.md agent files from *agents_dir*.

    The adlc-orchestrator is excluded — the authoring agent itself plays
    that role, so it would be redundant (and potentially recursive).
    """
    agents: dict[str, AgentDefinition] = {}
    for md_file in sorted(agents_dir.glob("adlc-*.md")):
        name, defn = _parse_agent_md(md_file)
        if name == "adlc-orchestrator":
            continue
        agents[name] = defn
    return agents
