---
name: run-evals
description: Run the ADLC evaluation framework — validate suites, evaluate generated agents with LLM-as-judge, generate reports
allowed-tools: Bash Read Write
argument-hint: "[--suite <suite.json>] [--generate] [--validate-only]"
---

# ADLC Evals

LLM-as-judge evaluation framework for the ADLC skill toolchain.

**Current scope:** the `agent` surface — `.agent` files produced by
`/adlc-author`. The suite JSON's `"surface"` field is the extension point
for evaluating other skills (`scaffold` → Flow/Apex XML, `safety` → review
reports, etc.), but the runner and judge only handle `agent` today.

## How it works

1. **Converse** — a simulated user (small LLM) has a multi-turn conversation
   with the skill under test, asking it to do something. The harness
   captures the resulting artifact plus full transcripts.
2. **Judge** — Claude evaluates the artifact against semantic assertions
   (FSM design, safety, intent capture). Not syntax — `sf agent validate`
   handles that.
3. **Report** — results roll up by assertion label and by test tag.

## Structure

```
evals/
├── runner.py      # CLI entry — run suites
├── reporter.py    # CLI entry — format results
├── harness.py     # conversational generation loop + simulated user
├── judge.py       # LLM-as-judge assertion checks
├── taxonomy.py    # ALL_LABELS + ALL_TAGS definitions
├── suites/        # test suite JSON files
└── results/       # run outputs (gitignored)
```

## Quick start

```bash
export ANTHROPIC_API_KEY=sk-ant-...
cd evals/

# Validate a suite (schema check only, no execution)
python runner.py --suite suites/basic-authoring.json --validate-only

# Full run: sim-user conversation → artifact → judge
python runner.py --suite suites/basic-authoring.json --generate

# Judge pre-built artifacts (skip the conversation)
python runner.py --suite suites/basic-authoring.json --agent-dir ./agents/ -o results.json

# Format results
python reporter.py results.json --format detailed
python reporter.py results.json --format markdown -o report.md
```

## CLI reference

### runner.py

| Flag | Description |
|---|---|
| `--suite, -s` | Path to suite JSON (required) |
| `--validate-only` | Check suite schema and exit |
| `--generate [DIR]` | Run conversational generation. DIR defaults to `results/run-<timestamp>` |
| `--agent-dir, -a` | Directory with pre-generated `<test-id>.agent` files |
| `--test-ids, -t` | Run only these test IDs |
| `--output, -o` | Write results JSON here |
| `--model, -m` | Judge model |
| `--sim-model` | Simulated-user model |
| `--max-turns` | Max conversation turns per test |
| `--verbose, -v` | Stream agent activity to stdout |

### reporter.py

| Flag | Description |
|---|---|
| `results` | Path to results JSON (positional) |
| `--format, -f` | `summary` (default), `detailed`, `failures`, `markdown`, `json` |
| `--output, -o` | Write to file instead of stdout |

### harness.py (standalone)

Run a single ad-hoc conversation without a suite:

```bash
python harness.py "Build an FAQ agent for product returns" --test-id my-test
```

## Suite format

```json
{
  "name": "Suite Name",
  "surface": "agent",
  "tests": [
    {
      "id": "test-id",
      "prompt": "What the sim user asks the skill to do",
      "goal": "Optional: sim-user follow-up script (e.g. ask for revision, then DONE)",
      "tags": ["customer-service", "medium", "verification-gate"],
      "assertions": [
        "[fsm:verification-gate] Identity check required before account access",
        "[safety:ai-disclosure] Agent identifies as AI"
      ],
      "negative_assertions": [
        "[safety:no-impersonation] Does NOT claim to be human"
      ]
    }
  ]
}
```

**`surface`:** which ADLC skill's output is under test. Only `agent`
(`.agent` files from `/adlc-author`) is implemented; `scaffold`, `safety`,
etc. are future extension points.

**`prompt` vs `goal`:** If `goal` is omitted, the harness stops as soon as
the artifact appears on disk. If `goal` is set, the simulated user drives
the conversation (e.g. requests a revision) and terminates by replying
`DONE`.

## Labels and tags

**Assertion labels** describe what capability is being tested. Most labels
judge the final `.agent` file; `process:*` labels judge the authoring
session transcript (conversation + activity logs):

| Category | Judged against | Examples |
|---|---|---|
| `structure:*` | `.agent` file | `linked-vars`, `system-messages` |
| `fsm:*` | `.agent` file | `no-orphan-topics`, `verification-gate`, `escalation-topic` |
| `actions:*` | `.agent` file | `level1-definition`, `slot-filling`, `output-capture` |
| `logic:*` | `.agent` file | `post-action-top`, `after-reasoning`, `conditional-flow` |
| `safety:*` | `.agent` file | `ai-disclosure`, `no-impersonation`, `scope-boundaries` |
| `chat:*` | `.agent` file | `welcome-message`, `topic-routing`, `guardrail-deflection` |
| `instructions:*` | `.agent` file | `procedural-mode`, `actionable`, `no-ambiguity` |
| `process:*` | session logs | `asked-clarifying`, `self-validated`, `first-write-valid`, `no-tool-thrashing` |

`process:*` assertions only work with `--generate` (the logs have to exist).
With `--agent-dir` pre-generated files there's no transcript to judge.

**Test tags** describe what domain/pattern the test covers:

| Category | Examples |
|---|---|
| Domain | `customer-service`, `hr-agent`, `healthcare`, `financial-services` |
| Pattern | `multi-topic`, `verification-gate`, `linear-flow` |
| Complexity | `minimal`, `easy`, `medium`, `hard` |
| Feature | `action-chaining`, `slot-filling`, `after-reasoning` |
| Safety | `safety-critical`, `pii-handling`, `regulated-domain` |

Full list with descriptions:

```bash
python -c "from evals.taxonomy import ALL_LABELS; [print(f'{k:35s} {v}') for k,v in ALL_LABELS.items()]"
python -c "from evals.taxonomy import ALL_TAGS;   [print(f'{k:25s} {v}') for k,v in ALL_TAGS.items()]"
```

**Scope note:** labels cover semantic quality only. Syntax, required blocks,
and deploy-readiness belong to `sf agent validate` — if the compiler catches
it, don't write an assertion for it.

## Output layout

Each test runs in an isolated scratch workspace so the generated `.agent`
file lands in a clean directory — no collisions with prior runs or other
tests in the suite.

```
results/run-<timestamp>/
├── eval_results.json        # suite-level results
└── <test-id>/
    ├── workspace/           # isolated cwd for the authoring agent
    │   ├── sfdx-project.json
    │   ├── .claude/         # symlink → repo .claude/ (skills)
    │   ├── CLAUDE.md        # symlink → repo CLAUDE.md
    │   └── force-app/main/default/aiAuthoringBundles/
    │       └── <Name>/<Name>.agent   # the generated agent
    ├── transcript.jsonl     # symlink → SDK's native jsonl
    ├── activity.log         # tool-call trace (tailable)
    └── conversation.log     # user ↔ agent text
```

## CI integration

```bash
python runner.py --suite suites/basic-authoring.json --generate -o results.json
python -c "import json,sys; r=json.load(open('results.json')); sys.exit(0 if r['overall_score'] >= 0.8 else 1)"
```
