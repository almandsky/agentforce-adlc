# ADLC Authoring Agent

A standalone Claude Agent SDK agent that wraps the entire Agentforce ADLC
toolchain — skills, subagents, and helper scripts — behind a single
conversational interface.

Built on the [`harness`](../../create-claude-agent) package
(`create-agent-sdk-app`).

## What it does

The Authoring Agent owns the full Agent Development Life Cycle:

1. **Author** — generate `.agent` files from plain-English requirements
2. **Discover** — check which Flow/Apex/Retriever targets exist in the org
3. **Scaffold** — generate metadata stubs for missing targets
4. **Deploy** — push, publish, and activate agent bundles
5. **Test** — run agent preview and batch smoke tests
6. **Optimize** — analyze session traces and iterate

It has access to every `/adlc-*` skill in this repo, can delegate to the
`adlc-author`, `adlc-engineer`, and `adlc-qa` subagents, and can run the
Python helper scripts under `scripts/`.

## Running

### CLI

```bash
cd authoring-agent
python3 cli.py
```

### FastAPI server

```bash
cd authoring-agent
python3 server.py
# or: uvicorn server:app --reload
```

Then open http://localhost:8000.

## Architecture

```
authoring-agent/
├── agent.py      create_agent() factory — options, prompt, subagents
├── subagents.py  parses agents/*.md → AgentDefinition
├── server.py     FastAPI entry (harness.create_app)
├── cli.py        CLI entry (harness.run_cli)
└── sessions/     per-session sandboxes (gitignored)
```

The agent's `cwd` is the repo root, so:

- Skills load from `.claude/skills/` (symlinked to `skills/`)
- Bash commands can call `python3 scripts/discover.py` directly
- The harness sandbox whitelists `.claude/` for read-only access and
  confines all writes to `sessions/<id>/sandbox/`

## Prerequisites

- `create-agent-sdk-app` installed (editable install from the sibling
  `create-claude-agent` repo)
- `ANTHROPIC_API_KEY` set
- Salesforce CLI authenticated against your target org (for deploy/run/test)
