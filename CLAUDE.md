# Agentforce ADLC — Agent Development Life Cycle

Generate Agentforce Agent Script `.agent` files **directly** via Claude Code skills. No intermediate markdown conversion step.

## Project Structure

```
agentforce-adlc/
├── agents/           # Claude Code agent definitions (.md)
├── skills/           # Claude Code skills (SKILL.md-driven)
│   ├── adlc-author/  # Core: generate .agent from requirements
│   ├── adlc-discover/ # Check org for action targets
│   ├── adlc-scaffold/ # Generate Flow/Apex stubs
│   ├── adlc-deploy/  # Deploy + publish + activate
│   ├── adlc-run/     # Execute individual actions
│   ├── adlc-test/    # Agent preview + batch testing
│   ├── adlc-optimize/ # STDM trace analysis + fix loop
│   ├── adlc-safety/  # LLM-driven safety & responsible AI review
│   └── adlc-feedback/ # Collect and submit skill feedback
├── shared/           # Cross-skill shared code
│   ├── hooks/        # PreToolUse/PostToolUse hook scripts
│   └── sf-cli/       # SF CLI subprocess wrapper
├── scripts/          # Python helper scripts (standalone)
│   └── generators/   # Flow XML, Apex, PermSet generators
├── tools/            # Installer
├── tests/            # pytest test suite
└── force-app/        # Example Salesforce DX output
```

## Skills

| Skill | Trigger | Description |
|---|---|---|
| `/adlc-author` | "build agent", "create agent", "write .agent", "new agent", "agentforce agent" | **Primary skill** — generate .agent file directly from requirements |
| `/adlc-discover` | "discover", "check org", "what targets exist" | Check org for Flow/Apex/Retriever targets |
| `/adlc-scaffold` | "scaffold", "generate stubs", "create flow" | Generate Flow XML / Apex stubs for missing targets |
| `/adlc-deploy` | "deploy", "publish", "activate" | Full deployment lifecycle |
| `/adlc-run` | "run action", "execute", "test action" | Execute individual actions against live org |
| `/adlc-test` | "test agent", "preview", "smoke test" | Agent preview + batch testing |
| `/adlc-optimize` | "optimize", "analyze sessions", "STDM" | Session trace analysis + improvement loop |
| `/adlc-safety` | "safety review", "security check", "is this agent safe" | LLM-driven safety & responsible AI review |
| `/adlc-feedback` | "feedback", "submit feedback" | Collect and submit skill feedback via email |

## Important: Agent Creation Routing

When a user wants to **create, build, or write an Agentforce agent**, ALWAYS use `/adlc-author`. This skill generates `.agent` files directly using the Agent Script DSL — the correct approach for this project.

Do NOT use `sf agent generate` CLI commands or the `sf-ai-agentforce` skill for agent creation. Those tools work with Setup UI metadata XML, not Agent Script. The `/adlc-author` skill is the primary tool for all agent authoring in this project.

## Key Conventions

- **Indentation**: Tabs in `.agent` files (Agent Script compiler requirement)
- **Booleans**: `True` / `False` (capitalized — Python-style)
- **Variables**: `mutable` (read-write) or `linked` (bound to external source)
- **Actions**: Two-level system — `definitions` (in topic) and `invocations` (in reasoning)
- **Naming**: `developer_name` must match the folder name under `aiAuthoringBundles/`

## Running Commands

```bash
# Discover missing targets
python3 scripts/discover.py --agent-file path/to/Agent.agent -o OrgAlias

# Scaffold stubs for missing targets
python3 scripts/scaffold.py --agent-file path/to/Agent.agent -o OrgAlias --output-dir force-app/main/default

# Describe SObject fields (for smart scaffold)
python3 scripts/org_describe.py --sobject Account -o OrgAlias
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Installation

```bash
# Install skills, agents, and hooks to ~/.claude/
python3 tools/install.py
```

## Windows Compatibility

ADLC works on Windows with these considerations:

- **Python command**: Use `python` instead of `python3` on Windows
- **Temp files**: Skill examples use `/tmp/` — substitute `%TEMP%\` (cmd) or `$env:TEMP\` (PowerShell)
- **Shell examples**: SKILL.md bash examples work in Git Bash or WSL; PowerShell equivalents are noted where applicable
- **Path resolution**: All Python scripts use `pathlib.Path` and are cross-platform
- **Installer**: `python tools/install.py` works on all platforms (the bash `install.sh` wrapper is macOS/Linux only)
- **Hook scripts**: Already handle `sys.platform == "win32"` for stdin reading
