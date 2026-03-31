# ADLC Eval — Agent Quality Evaluation Framework

Automated evaluation framework for Agentforce agents built with the ADLC skills. Runs test suites against installed `/agentforce-*` skills, judges outputs against assertion criteria, and generates interactive HTML reports.

## Quick Start

```bash
cd evals
claude

# Run a test suite
run suite basic-authoring

# Run a single test
run suite basic-authoring --test-id hello-world-faq

# Re-judge existing results
run suite basic-authoring --judge-only results/run-20260327-143000

# Compare two runs
run suite full-pipeline --compare results/run-20260326-120000
```

## How It Works

The eval framework is an **orchestrator and judge** — it delegates all agent generation, testing, and optimization to the installed `/agentforce-*` skills (the same way a user would), then evaluates the outputs.

### 4-Phase Workflow

| Phase | What Happens |
|-------|-------------|
| **0. Spec & Discovery** | Load/generate agent spec, discover installed `/agentforce-*` skills |
| **1. Load Suite** | Read test suite JSON, validate structure, apply filters |
| **2. Execute Pipeline** | Invoke `/agentforce-development` (author, discover, scaffold, deploy), `/agentforce-test`, `/agentforce-observability` per test's `pipeline` field |
| **3. Judge** | Evaluate outputs against spec-derived + suite-defined assertions using taxonomy labels |
| **4. Report** | Aggregate scores, generate `summary.json`, produce HTML report |

## Directory Structure

```
evals/
├── .claude/                # Project-scoped eval settings & skills
│   ├── settings.local.json # Permissions for eval skills
│   └── skills/             # Eval-specific skills (not installed globally)
│       ├── eval-spec/      # Generate agent specs from prompts
│       ├── eval-author-judge/  # Judge authoring quality
│       ├── eval-test-judge/    # Judge test results
│       └── eval-report/    # Generate reports
├── suites/                 # Test suite definitions (JSON)
│   ├── basic-authoring.json
│   ├── complex-multi-topic.json
│   ├── safety-guardrails.json
│   └── full-pipeline.json
├── specs/                  # Agent spec documents
├── templates/              # Spec and report templates
├── results/                # Test run outputs (gitignored)
├── taxonomy.py             # 65 assertion labels across 11 categories
├── rubric.py               # Per-skill weighted scoring dimensions
├── reporter.py             # CLI output formatter (text/markdown/json/html)
├── generate-report.py      # Interactive HTML report generator
├── CLAUDE.md               # Eval orchestrator instructions
└── ARCHITECTURE.md         # Design decisions and data flow
```

## Test Suites

| Suite | Tests | Description |
|-------|-------|-------------|
| `basic-authoring` | 5 | Single-topic agents, minimal complexity |
| `complex-multi-topic` | 3 | Multi-topic agents with actions, transitions, verification gates |
| `safety-guardrails` | 4 | Agents in regulated domains (medical, financial, legal, children) |
| `full-pipeline` | 3 | End-to-end: author → discover → scaffold → deploy → test → optimize |

### Suite JSON Format

```json
{
  "name": "Suite Name",
  "version": "1.0",
  "surface": "agent",
  "tests": [
    {
      "id": "test-id",
      "prompt": "Build an agent that...",
      "pipeline": ["author"],
      "tags": ["easy", "faq-bot"],
      "assertions": [
        "[safety:ai-disclosure] System instructions identify this as an AI",
        "[fsm:hub-and-spoke] Agent uses hub-and-spoke routing pattern"
      ]
    }
  ]
}
```

## Assertion Taxonomy

Labels follow the format `category:specific-check`. Categories:

| Category | Examples | What It Checks |
|----------|---------|----------------|
| `fsm:` | hub-and-spoke, no-dead-ends, reachable | FSM architecture quality |
| `actions:` | definition-complete, io-schema, target-format | Action configuration |
| `safety:` | ai-disclosure, domain-boundaries, escalation | Safety & responsible AI |
| `instructions:` | procedural-mode, variable-injection | Instruction quality |
| `process:` | requirements-gathered, validation-run | Authoring process |
| `structure:` | config-complete, system-messages | File structure |
| `discover:` | target-found, fuzzy-match | Org discovery accuracy |
| `scaffold:` | compiles, field-mapping | Scaffold quality |
| `deploy:` | clean-deploy, publish-success | Deployment success |
| `test:` | smoke-pass, utterance-coverage | Test coverage |
| `optimize:` | issue-identified, fix-applied | Optimization quality |
| `pipeline:` | skill-routing, artifact-chain | Cross-skill flow |

See `taxonomy.py` for the complete list of 65 labels.

## Scoring

Each skill has weighted dimensions defined in `rubric.py`:

- **Author**: FSM architecture (25%), action quality (20%), safety compliance (20%), instruction quality (15%), process quality (10%), conversational (10%)
- **Deploy**: clean deploy (40%), component count (20%), publish success (20%), activate success (20%)
- **Test**: smoke pass (35%), utterance coverage (30%), conversation quality (35%)
- **Optimize**: issue identified (30%), fix applied (30%), regression free (25%), STDM analyzed (15%)

Grades: A (90+), B (75-89), C (60-74), D (40-59), F (<40)

## Reports

### CLI Report
```bash
python3 reporter.py results/run-<timestamp>/summary.json --format detailed
```

### HTML Report
```bash
python3 generate-report.py results/run-<timestamp>/summary.json --output report.html
```

The HTML report is a single self-contained file with:
- Overall score and grade badge
- Per-skill dimension progress bars
- By-label pass/fail heatmap
- Expandable test case cards with pipeline visualization, assertion verdicts, and raw data tabs

## Key Principles

- **Never hardcode skill paths** — interact with skills only through `/agentforce-*` interface
- **Capture everything** — errors, logs, conversations, traces, fixes
- **Per-skill rubrics** — different evaluation dimensions per skill
- **Spec-driven** — all judging is against the agent spec, not just assertions
- **Results are local** — `results/` is gitignored, each run gets a timestamped directory
- **Not installed globally** — eval skills live in `evals/.claude/skills/`, not in `~/.claude/`

## Special Thanks

- [**Joe Shamon**](https://github.com/jsham042) — for his contribution to the evaluations of the ADLC skills
