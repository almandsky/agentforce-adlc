# agentforce-adlc

**Agent Development Life Cycle** — Generate Agentforce Agent Script `.agent` files directly via Claude Code skills.

## What is this?

`agentforce-adlc` provides a complete set of Claude Code skills and agents for building, deploying, testing, and optimizing Salesforce Agentforce agents using the Agent Script DSL. Unlike pipeline-based approaches, Claude writes `.agent` files directly — no intermediate conversion step.

## Quick Start

```bash
# Install to Claude Code
python3 tools/install.py

# Then in any Salesforce DX project:
/adlc-author    # Build an agent from requirements
/adlc-deploy    # Deploy to your org
/adlc-test      # Run smoke tests
```

## Workflow

```
Requirements → /adlc-author → .agent file
                    ↓
              /adlc-discover → check org targets
                    ↓
              /adlc-scaffold → generate Flow/Apex stubs
                    ↓
              /adlc-deploy → validate → publish → activate
                    ↓
              /adlc-test → smoke test → fix loop
                    ↓
              /adlc-optimize → STDM analysis → improve
```

## Requirements

- Python 3.10+
- Salesforce CLI (`sf`) v2.x
- Claude Code
- A Salesforce org with Agentforce enabled

## License

MIT
