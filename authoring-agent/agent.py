"""ADLC Authoring Agent — factory for the Claude Agent SDK harness.

Points the agent at the agentforce-adlc repo root so that:
  * skills load from .claude/skills/ (symlinked to the repo's skills/)
  * Bash commands can invoke scripts/*.py with relative paths
  * the harness sandbox whitelists .claude/ for read-only access

The adlc-author/engineer/qa subagents are loaded from agents/*.md and
exposed via the Task tool so the authoring agent can delegate to them.
"""

from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

from subagents import load_adlc_agents

REPO_ROOT = Path(__file__).resolve().parents[1]


def create_agent() -> ClaudeAgentOptions:
    """Build the ADLC Authoring Agent options for the harness."""
    return ClaudeAgentOptions(
        model="claude-opus-4-6",
         cwd=str(REPO_ROOT),
        setting_sources=["project"],
        allowed_tools=[
            "Read", "Write", "Edit", "MultiEdit",
            "Bash", "Grep", "Glob", "LS",
            "Task", "Skill", "TodoWrite", "WebFetch",
        ],
        agents=load_adlc_agents(REPO_ROOT / "agents"),
        permission_mode="acceptEdits",
        add_dirs=[str(REPO_ROOT)],
    )
