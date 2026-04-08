# ADLC Eval — Multi-Agent Architecture

## Problem Statement

The current eval framework has a single Claude Code session doing everything:
- Running ADLC skills (author, test, optimize)
- Judging assertions (PASS/FAIL with brief reasons)
- Generating reports

**Result: shallow, high-level reports that don't explain WHY things work or fail.**

The verdicts say things like "PASS — hub-and-spoke pattern present" but never synthesize:
- What design decisions the author made and whether they were good
- Why a specific failure happened at the platform level
- What the business impact of each issue is
- What the recommended fix path is
- How this compares to known best practices

## Design Principles

1. **Spec is ground truth** — Every eval starts with a spec that defines what "good" looks like
2. **Specialized judges** — Each lifecycle step has a dedicated evaluator with domain expertise
3. **Structured capture** — Every skill produces machine-readable results, not ad-hoc text
4. **Insights over scores** — Each verdict includes WHY (root cause), SO WHAT (impact), and NOW WHAT (recommendation)
5. **Composable** — Skills can run independently or orchestrated together

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   eval-orchestrator                      │
│  (CLAUDE.md — the agent that coordinates everything)    │
│                                                         │
│  Phase 0: Load suite → create/validate spec             │
│  Phase 1: Run pipeline (delegate to agentforce-* skills) │
│  Phase 2: Delegate judging to eval-* skills             │
│  Phase 3: Collect results → generate report              │
└──────────┬──────────┬──────────┬──────────┬─────────────┘
           │          │          │          │
    ┌──────▼──┐ ┌─────▼────┐ ┌──▼───┐ ┌───▼──────┐
    │eval-spec│ │eval-author│ │eval- │ │eval-     │
    │         │ │-judge     │ │test- │ │optimize- │
    │Create/  │ │           │ │judge │ │judge     │
    │validate │ │Analyze    │ │      │ │          │
    │agent    │ │.agent file│ │Run   │ │Analyze   │
    │spec from│ │against    │ │tests,│ │optimizer │
    │prompt or│ │spec.      │ │judge │ │findings, │
    │intake   │ │Explain    │ │each  │ │verify    │
    │         │ │design     │ │conv  │ │fixes,    │
    │         │ │choices.   │ │turn  │ │judge     │
    │         │ │           │ │      │ │quality   │
    └─────────┘ └───────────┘ └──────┘ └──────────┘
                      │
              ┌───────▼────────┐
              │  eval-report   │
              │                │
              │  Synthesize    │
              │  all results   │
              │  into insights │
              │  report        │
              └────────────────┘
```

## Eval Skills

### `/eval-spec` — Spec Creator & Validator

**Input:** Test prompt, or interactive intake interview
**Output:** `spec.md` + derived assertions

**What it does:**
1. Parse the prompt to extract topics, actions, patterns, safety requirements
2. Ask follow-up questions if information is missing
3. Fill in the spec template (templates/agent-spec.md)
4. Generate assertions from spec sections
5. Validate completeness (all sections filled, scenarios defined)

**Result schema:**
```json
{
  "spec_path": "results/run-<ts>/<test-id>/spec.md",
  "completeness": {
    "topics_defined": 4,
    "actions_defined": 6,
    "scenarios_defined": 5,
    "safety_defined": true,
    "verification_defined": true
  },
  "derived_assertions": ["[fsm:hub-and-spoke] ...", ...],
  "inferred_fields": ["brand_voice", "resolution_target"],
  "confidence": 0.92
}
```

### `/eval-author-judge` — Agent Script Analyst

**Input:** `.agent` file + `spec.md`
**Output:** Deep analysis of authoring quality

**What it does (NOT just PASS/FAIL):**
1. **Structural analysis** — Map the .agent file structure (topics, actions, variables, transitions)
2. **Spec compliance** — Compare every spec requirement against the .agent file
3. **Design review** — Evaluate architectural choices:
   - Is this FSM pattern appropriate for the use case?
   - Are the topic boundaries well-drawn?
   - Are instructions clear enough for the LLM?
   - Will the available-when guards work at runtime?
4. **Risk assessment** — Identify likely runtime issues:
   - Will this cause SMALL_TALK grounding? (intermediate actions with no data)
   - Will slot-filling work? (correct ... syntax)
   - Will routing work? (start_agent instructions strong enough)
5. **Recommendations** — Specific, actionable fixes

**Result schema:**
```json
{
  "analysis": {
    "structure": {
      "topics": [{"name": "product_search", "actions": 1, "transitions": 2, "has_instructions": true}],
      "total_topics": 4,
      "total_actions": 6,
      "total_variables": 8,
      "fsm_pattern": "hub-and-spoke",
      "has_verification_gate": true,
      "has_after_reasoning": true
    },
    "spec_compliance": {
      "topics_match": true,
      "actions_match": true,
      "missing_from_spec": [],
      "extra_not_in_spec": ["topic_selector"],
      "type_mismatches": [{"action": "search_products", "field": "max_price", "spec": "number", "actual": "string"}]
    },
    "design_review": {
      "strengths": [
        "Router-only start_agent with explicit 'do not answer' instruction — prevents SMALL_TALK",
        "Clean hub-and-spoke with no orphan topics",
        "after_reasoning in pickup guarantees deterministic scheduling"
      ],
      "weaknesses": [
        "set_associate + available_when two-step pattern will cause SMALL_TALK on employee_hr",
        "max_price/bedrooms typed as string instead of object with complex_data_type_name"
      ],
      "risks": [
        {
          "severity": "high",
          "issue": "Employee HR verification gate will fail at runtime",
          "reason": "set_associate produces no user-facing data, so the platform's grounding check will reject it as SMALL_TALK before the second reasoning turn can fire view_schedule",
          "recommendation": "Use literal instructions with explicit tool names instead of two-step pattern. Or remove the gate and pass employee_id directly via slot-filling.",
          "known_pattern": "setVariables gating — see MEMORY.md"
        }
      ]
    },
    "verdicts": [
      {
        "assertion": "[fsm:hub-and-spoke] ...",
        "label": "fsm:hub-and-spoke",
        "result": "PASS",
        "confidence": 0.98,
        "reason": "start_agent routes to 4 topics via transition actions",
        "evidence": "start_agent hub_router: actions: to_product_search, to_inventory...",
        "insight": "Good pattern choice — hub-and-spoke is ideal for multi-domain agents with independent topics",
        "impact": "Correct routing ensures users reach the right topic on first turn",
        "recommendation": null
      }
    ]
  }
}
```

### `/eval-test-judge` — Conversation & Trace Analyst

**Input:** `conversations.json` + `scenarios.json` + trace files + `spec.md`
**Output:** Deep analysis of each conversation turn

**What it does:**
1. **Per-utterance trace analysis:**
   - Which topic handled it? Was that correct per spec?
   - Which actions were available? Which was invoked?
   - Was the response grounded? If SMALL_TALK, explain why
   - How many reasoning steps? (retry detection)
   - What was the safety score?
2. **Conversation quality:**
   - Does the response advance the user's goal?
   - Is the tone appropriate for the domain?
   - Does the agent ask for info it already has? (repetition)
   - Does it suggest next steps? (proactive guidance)
3. **Scenario evaluation:**
   - Did the multi-turn flow match the spec?
   - Were parameters extracted correctly?
   - Was the task completed within max_turns?
4. **Root cause analysis for failures:**
   - SMALL_TALK: What data was missing? Was it an intermediate action?
   - Wrong topic: Was the topic description too vague? Overlapping keywords?
   - Wrong action: Was the action description ambiguous?
   - Deflection: Was the LLM told to ask instead of act?

**Result schema:**
```json
{
  "utterance_results": [
    {
      "utterance": "I'm looking for a Nintendo Switch",
      "result": "PASS",
      "topic": {"expected": "product_search", "actual": "product_search", "match": true},
      "action": {"expected": "search_products", "actual": "search_products", "match": true},
      "grounding": "GROUNDED",
      "safety_score": 0.98,
      "reasoning_steps": 1,
      "response_quality": {
        "advances_goal": true,
        "tone_appropriate": true,
        "suggests_next_steps": true
      },
      "insight": "Clean routing: start_agent correctly identified product intent and routed to product_search topic. search_products action invoked with query='Nintendo Switch'. Response includes product variants and accessories."
    },
    {
      "utterance": "I'm employee E5521, can I see my schedule?",
      "result": "FAIL",
      "topic": {"expected": "employee_hr", "actual": "hub_router", "match": false},
      "grounding": "SMALL_TALK",
      "reasoning_steps": 2,
      "root_cause": {
        "category": "GROUNDING_REJECTION",
        "explanation": "The platform routed to employee_hr and invoked set_associate, but set_associate is a @utils.setVariables action that produces no user-facing data. The grounding system classified the response as SMALL_TALK because there was no factual content from an action result. The system retried (2 ReasoningSteps) but failed again.",
        "platform_limitation": true,
        "known_issue": "setVariables gating causes SMALL_TALK — documented in MEMORY.md"
      },
      "recommendation": "Replace two-step verification with literal instructions that explicitly call set_associate then immediately call view_schedule in the same turn, or pass employee_id directly via slot-filling."
    }
  ],
  "scenario_results": [...],
  "business_metrics": {
    "containment_rate": 0.80,
    "grounding_rate": 0.75,
    "action_accuracy": 1.0,
    "avg_turns_to_resolution": 2.0
  },
  "summary": {
    "total_utterances": 4,
    "passed": 3,
    "failed": 1,
    "key_finding": "3/4 topics route correctly. Employee HR fails due to platform grounding rejection of intermediate setVariables action. This is the #1 production failure pattern for gated topics.",
    "recommended_fix": "Use literal instructions with explicit tool names for the HR topic, or remove the verification gate and pass employee_id directly."
  }
}
```

### `/eval-optimize-judge` — Optimization Analyst

**Input:** Optimize invocation data + .agent diffs + trace data + `spec.md`
**Output:** Analysis of optimization quality

**What it does:**
1. **Issue detection quality** — Did the optimizer find the real issues?
2. **Fix quality** — Are fixes correct? Do they drift from the spec?
3. **Regression safety** — Did fixes break other topics?
4. **Convergence** — How many iterations? Did it converge or give up?
5. **Spec alignment** — Does the optimized agent still match the spec?

### `/eval-report` — Report Synthesizer

**Input:** All judge results + spec + pipeline metadata
**Output:** Interactive HTML report with insights

**What it does:**
1. **Executive summary** — 3-sentence overview: what was tested, what worked, what didn't
2. **Key findings** — Top 3-5 insights ranked by business impact
3. **Per-test deep dive** — Full analysis from each judge skill
4. **Spec compliance matrix** — Visual grid: spec requirement vs actual
5. **Recommendations** — Prioritized action items
6. **Comparison** — Delta from previous run (if --compare)

## Verdict Schema (Enhanced)

Every verdict from every judge skill uses this schema:

```json
{
  "assertion": "[label] description",
  "label": "fsm:hub-and-spoke",
  "result": "PASS|FAIL|SKIP",
  "confidence": 0.95,
  "reason": "Short explanation of what was found",
  "evidence": "Relevant snippet from the output",
  "insight": "WHY this matters — design rationale or root cause",
  "impact": "SO WHAT — business/user impact of this result",
  "recommendation": "NOW WHAT — specific fix if FAIL, or null if PASS"
}
```

The three new fields (`insight`, `impact`, `recommendation`) are what turn a checklist into useful analysis.

## Implementation Plan

### Phase 1: Eval Skills (Claude Code skills)

Create these as Claude Code skills under `skills/`:

```
skills/
  eval-spec/SKILL.md          — Spec creator
  eval-author-judge/SKILL.md  — Agent script analyst
  eval-test-judge/SKILL.md    — Conversation & trace analyst
  eval-optimize-judge/SKILL.md — Optimization analyst
  eval-report/SKILL.md        — Report synthesizer
```

Each skill:
- Has its own SKILL.md with domain expertise and evaluation criteria
- Produces structured JSON results (not free-form text)
- Can run independently (e.g., `/eval-author-judge path/to/Agent.agent specs/target-store.md`)
- Includes known patterns and failure modes from MEMORY.md

### Phase 2: Orchestrator Update

Update `evals/CLAUDE.md` to delegate to eval skills:

```
Phase 0: /eval-spec → create spec
Phase 1: /developing-agentforce, /testing-agentforce, etc. → run pipeline
Phase 2: /eval-author-judge, /eval-test-judge, /eval-optimize-judge → judge
Phase 3: /eval-report → synthesize and generate HTML
```

### Phase 3: Report Upgrade

Update `generate-report.py` to consume the richer verdict schema:
- Show insight/impact/recommendation for each verdict
- Add "Key Findings" section
- Add "Spec Compliance Matrix"
- Show root cause analysis for failures
- Show design review strengths/weaknesses

## File Layout

```
evals/
  CLAUDE.md              — Orchestrator (updated to delegate to eval skills)
  ARCHITECTURE.md        — This file
  templates/
    agent-spec.md        — Spec template
  specs/
    target-store-assistant.md  — Example spec
  suites/
    *.json               — Test suite definitions
  taxonomy.py            — Assertion labels
  rubric.py              — Scoring dimensions
  generate-report.py     — HTML report generator
  reporter.py            — CLI reporter

skills/
  eval-spec/SKILL.md
  eval-author-judge/SKILL.md
  eval-test-judge/SKILL.md
  eval-optimize-judge/SKILL.md
  eval-report/SKILL.md
```

## How It Works End-to-End

```
User: run suite full-pipeline --test-id target-store-full-cycle --org epson

Orchestrator:
  1. Load suite, find test
  2. /eval-spec → reads prompt, creates spec.md with 4 topics, 6 actions, 5 scenarios
  3. /developing-agentforce → generates TargetStoreAssistant.agent
  4. /eval-author-judge → analyzes .agent against spec
     → "Hub-and-spoke correct. But set_associate gating will cause SMALL_TALK (high risk)."
     → "max_price typed as string, spec says number (medium risk)."
  5. /developing-agentforce (discover) → finds 0/6 targets in org
  6. /developing-agentforce (scaffold) → generates 22 stub files
  7. /developing-agentforce (deploy) → deploys 71 components, publishes, activates
  8. /testing-agentforce → runs 6 utterances + 5 scenarios
  9. /eval-test-judge → analyzes each conversation turn
     → "3/4 smoke tests pass. Employee HR fails: SMALL_TALK on set_associate."
     → "Root cause: intermediate action produces no factual content."
     → "4/5 scenarios pass. HR scenario fails at turn 1."
  10. /observing-agentforce → finds issue, applies fix in 5 iterations
  11. /eval-optimize-judge → evaluates optimization
      → "Optimizer correctly identified SMALL_TALK issue."
      → "Fix removed verification gate — spec deviation (acceptable tradeoff)."
      → "4/4 regression tests pass."
  12. /eval-report → synthesize all results into HTML
      → Executive summary, key findings, spec compliance, recommendations
```
