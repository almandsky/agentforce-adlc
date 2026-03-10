# agentforce-adlc

**Agent Development Life Cycle** — Build, deploy, test, and optimize Agentforce agents
using Claude Code skills and Agent Script DSL.

## What is this?

`agentforce-adlc` provides a complete set of Claude Code skills for the full Agentforce agent lifecycle — from requirements to production optimization. Claude writes `.agent` files directly using the Agent Script DSL. No intermediate markdown conversion step.

### Key differentiators

- **Direct authoring** — Claude generates `.agent` files natively, not via markdown-to-agent conversion
- **Full lifecycle** — Author, discover, scaffold, deploy, test, and optimize in one toolchain
- **Deterministic agents** — Agent Script DSL enforces code-level guarantees (conditionals, guards, transitions)
- **Session trace analysis** — Extract STDM data from Data Cloud for data-driven optimization
- **Skill-based** — Each lifecycle phase is a standalone Claude Code skill, usable independently

## Pipeline

```
User prompt
  │  /adlc-author
  ▼
┌─────────────────────────┐
│  .agent file generated  │
└────────┬────────────────┘
         │  /adlc-discover
         ▼
┌─────────────────────────┐
│  Check org for targets  │──missing──▶ /adlc-scaffold
└────────┬────────────────┘
         │  /adlc-deploy
         ▼
┌─────────────────────────┐
│  Validate → Publish →   │
│  Activate               │
└────────┬────────────────┘
         │  /adlc-test
         ▼
┌─────────────────────────┐
│  Preview + Testing      │
│  Center batch tests     │
└────────┬────────────────┘
         │  /adlc-optimize
         ▼
┌─────────────────────────┐
│  STDM session analysis  │
│  → Reproduce → Improve  │
└─────────────────────────┘
```

Each skill can be invoked independently. Run `/adlc-test` on an existing agent without touching the author/deploy steps. Run `/adlc-optimize` on production session data without redeploying.

## Installation

### One-command install (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/Authoring-Agent/agentforce-adlc/main/tools/install.sh | bash
```

### From local clone

```bash
git clone https://github.com/Authoring-Agent/agentforce-adlc.git
cd agentforce-adlc
python3 tools/install.py
```

### Post-install management

```bash
# Check what's installed
python3 ~/.claude/adlc-install.py --status

# Update to latest version
python3 ~/.claude/adlc-install.py --update

# Force reinstall
python3 ~/.claude/adlc-install.py --force-update

# Remove everything
python3 ~/.claude/adlc-install.py --uninstall
```

After install, restart Claude Code. Skills are available in any project.

## Prerequisites

- **Python 3.10+**
- **Salesforce CLI** (`sf`) v2.x — [install guide](https://developer.salesforce.com/tools/salesforcecli)
- **Claude Code** — `~/.claude/` directory must exist
- **Salesforce org** with Agentforce enabled

## Quick start

### 1. Author an agent

```
/adlc-author

Build a service agent for Lennar that helps home buyers search communities,
find floor plans, and check pricing. It should verify identity before
showing pricing details.
```

Claude generates a `.agent` file with topics, actions, variables, and deterministic logic.

### 2. Check what exists in the org

```
/adlc-discover

Check what targets exist for LennarHomeSearch.agent against the epson org.
```

Reports which Flow/Apex/Retriever targets already exist and which need creation.

### 3. Scaffold missing targets

```
/adlc-scaffold

Generate Flow and Apex stubs for the missing targets.
```

Creates metadata XML for Flows and `@InvocableMethod` Apex classes matching the agent's action signatures.

### 4. Deploy to the org

```
/adlc-deploy

Deploy LennarHomeSearch to the epson org.
```

Validates the bundle, deploys prerequisites, publishes the authoring bundle, and activates the agent.

### 5. Test the agent

```
/adlc-test

Smoke test LennarHomeSearch against epson with these utterances:
- "I'm looking for homes in Austin"
- "Show me floor plans under $400k"
- "What communities have 4 bedrooms?"
```

Runs preview sessions, analyzes traces, and reports topic routing accuracy and action success rates.

### 6. Optimize from production data

```
/adlc-optimize

Analyze the last 50 sessions for LennarHomeSearch on epson.
Find routing failures and suggest improvements.
```

Extracts STDM session traces from Data Cloud, identifies patterns (wrong topic, missing actions, ungrounded responses), reproduces issues with live preview, and applies fixes directly to the `.agent` file.

## Skills reference

| Skill | Description | Trigger phrases |
|-------|-------------|-----------------|
| `/adlc-author` | Generate `.agent` files from requirements | "build agent", "create agent", "write .agent" |
| `/adlc-discover` | Check org for Flow/Apex/Retriever targets | "discover", "check org", "what targets exist" |
| `/adlc-scaffold` | Generate Flow XML / Apex stubs for missing targets | "scaffold", "generate stubs", "create flow" |
| `/adlc-deploy` | Validate, publish, and activate agent bundles | "deploy", "publish", "activate" |
| `/adlc-run` | Execute individual actions against a live org | "run action", "execute", "test action" |
| `/adlc-test` | Agent preview + Testing Center batch tests | "test agent", "preview", "smoke test" |
| `/adlc-optimize` | STDM session trace analysis + improvement loop | "optimize", "analyze sessions", "STDM" |

## Companion tools

`agentforce-adlc` works well alongside these related projects:

- **[agentforce-md](https://github.com/almandsky/agentforce-md)** — Convert Claude Code markdown conventions into Agent Script. Use when you prefer the markdown-first authoring approach.
- **[sf-skills](https://github.com/almandsky/sf-skills)** — General Salesforce Claude Code skills (Apex, LWC, Flow, deploy, etc.). Complements the ADLC agent-specific skills.

All three can be installed side-by-side without conflicts.

## Project structure

```
agentforce-adlc/
├── agents/              # Claude Code agent definitions (.md)
│   ├── adlc-orchestrator.md   # Plan-mode orchestrator
│   ├── adlc-author.md         # Agent Script authoring specialist
│   ├── adlc-engineer.md       # Platform engineer (discover/scaffold/deploy)
│   └── adlc-qa.md             # Testing and optimization specialist
├── skills/              # Claude Code skills (SKILL.md-driven)
│   ├── adlc-author/     # Generate .agent from requirements
│   ├── adlc-discover/   # Check org for action targets
│   ├── adlc-scaffold/   # Generate Flow/Apex stubs
│   ├── adlc-deploy/     # Deploy + publish + activate
│   ├── adlc-run/        # Execute individual actions
│   ├── adlc-test/       # Agent preview + batch testing
│   └── adlc-optimize/   # STDM trace analysis + fix loop
├── shared/              # Cross-skill shared code
│   ├── hooks/           # PreToolUse/PostToolUse hook scripts
│   │   ├── scripts/     # guardrails.py, agent-validator.py, session-init.py
│   │   └── skills-registry.json
│   └── sf-cli/          # SF CLI subprocess wrapper
├── scripts/             # Python helper scripts (standalone)
│   ├── discover.py      # CLI: discover missing targets
│   ├── scaffold.py      # CLI: scaffold Flow/Apex stubs
│   ├── org_describe.py  # CLI: describe SObject fields
│   └── generators/      # Flow XML, Apex, PermSet generators
├── tools/               # Installer
│   ├── install.py       # Python installer (local + remote)
│   └── install.sh       # Bash bootstrap for curl | bash
├── tests/               # pytest test suite
└── force-app/           # Example Salesforce DX output
```

### Post-install layout (`~/.claude/`)

```
~/.claude/
├── skills/
│   ├── adlc-author/SKILL.md
│   ├── adlc-discover/SKILL.md
│   ├── adlc-scaffold/SKILL.md
│   ├── adlc-deploy/SKILL.md
│   ├── adlc-run/SKILL.md
│   ├── adlc-test/SKILL.md
│   └── adlc-optimize/SKILL.md
├── agents/
│   ├── adlc-orchestrator.md
│   ├── adlc-author.md
│   ├── adlc-engineer.md
│   └── adlc-qa.md
├── hooks/
│   ├── scripts/
│   │   ├── adlc-guardrails.py
│   │   ├── adlc-agent-validator.py
│   │   ├── adlc-session-init.py
│   │   └── stdin_utils.py
│   └── skills-registry.json
├── adlc/                    # Full repo copy
├── adlc-install.py          # Self-updater
└── .adlc.json               # Install metadata
```

## Agent Script conventions

- **Indentation**: Tabs in `.agent` files (compiler requirement)
- **Booleans**: `True` / `False` (capitalized, Python-style)
- **Variables**: `mutable` (read-write) or `linked` (bound to external source)
- **Actions**: Two-level system — `definitions` (in topic) and `invocations` (in reasoning)
- **Naming**: `developer_name` must match the folder name under `aiAuthoringBundles/`
- **Instructions**: Literal (`|`) for static text, procedural (`->`) for conditional logic

## Development

```bash
# Clone and set up dev environment
git clone https://github.com/Authoring-Agent/agentforce-adlc.git
cd agentforce-adlc
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Install from local clone (for development)
python3 tools/install.py --force
```

### Standalone scripts

These scripts can be run directly without installing the skills:

```bash
# Discover missing targets
python3 scripts/discover.py --agent-file path/to/Agent.agent -o OrgAlias

# Scaffold stubs for missing targets
python3 scripts/scaffold.py --agent-file path/to/Agent.agent -o OrgAlias --output-dir force-app/main/default

# Describe SObject fields (for smart scaffold)
python3 scripts/org_describe.py --sobject Account -o OrgAlias
```

## License

MIT
