# ADLC Eval Improvements — Design Document

## What We Measure Today

Current evals focus on **structural correctness** of the authored .agent file and **pipeline mechanics**:

| Category | What We Check | What's Missing |
|----------|--------------|----------------|
| FSM Architecture | Hub-and-spoke, no orphans, no dead ends | Does the FSM actually solve the user's problem? |
| Actions | Correct targets, I/O types, slot-filling | Do the actions produce useful results for end users? |
| Safety | AI disclosure, scope boundaries, PII minimization | Adversarial robustness under real conversations |
| Pipeline | Artifact chain, skill routing, deploy success | End-to-end task completion rate |
| Test | Smoke pass, utterance coverage | Does the conversation actually resolve the user's need? |

**The core gap:** We measure *how well the agent is built* but not *whether it achieves business outcomes*.

---

## 1. Business Outcome Measurement

### New Assertion Category: `outcome:*`

```python
# New labels for taxonomy.py
"outcome:task-completion":    "Agent completes the user's intended task end-to-end",
"outcome:first-contact-resolution": "Issue resolved without escalation or follow-up",
"outcome:correct-action-selection": "Agent chose the right action for the user's intent",
"outcome:correct-parameters":  "Action called with correct parameter values",
"outcome:helpful-response":    "Response directly advances the user toward their goal",
"outcome:minimal-turns":       "Task completed in reasonable number of turns (not excessive)",
"outcome:appropriate-escalation": "Escalated at the right time — not too early, not too late",
```

### New Rubric Dimension: `outcome` skill

```python
"outcome": {
    "dimensions": {
        "task_completion":    {"weight": 35, "labels": ["outcome:task-completion", "outcome:first-contact-resolution"]},
        "action_accuracy":    {"weight": 30, "labels": ["outcome:correct-action-selection", "outcome:correct-parameters"]},
        "conversation_efficiency": {"weight": 20, "labels": ["outcome:minimal-turns", "outcome:helpful-response"]},
        "escalation_quality": {"weight": 15, "labels": ["outcome:appropriate-escalation"]},
    }
}
```

### How It Works

Each test case defines **scenarios** — multi-turn conversation scripts with expected outcomes:

```json
{
  "id": "order-status-e2e",
  "prompt": "Build a customer service agent for order tracking...",
  "scenarios": [
    {
      "name": "Happy path — check order status",
      "turns": [
        {"user": "What's the status of order ORD-1234?", "expect_action": "get_order_status", "expect_params": {"order_id": "ORD-1234"}},
        {"user": "Thanks!", "expect_topic": "topic_selector"}
      ],
      "expected_outcome": "task-completed",
      "max_turns": 4
    },
    {
      "name": "Edge case — no order found",
      "turns": [
        {"user": "Check order INVALID-999", "expect_action": "get_order_status"},
        {"user": "I want to talk to someone", "expect_action": "escalate"}
      ],
      "expected_outcome": "escalated-appropriately"
    },
    {
      "name": "Ambiguous — unclear intent",
      "turns": [
        {"user": "I have a problem", "expect_behavior": "asks-clarifying-question"}
      ],
      "expected_outcome": "clarification-given"
    }
  ]
}
```

The eval runner executes these scenarios via `sf agent preview` after deploy, then judges:
- Did the agent call the right action with the right parameters?
- Did the conversation resolve in a reasonable number of turns?
- Was the response helpful and on-topic?

---

## 2. Conversation Quality Scoring

### New Assertion Category: `conversation:*`

```python
"conversation:tone-appropriate":    "Response tone matches the domain (professional for finance, warm for hospitality)",
"conversation:no-repetition":       "Agent doesn't repeat the same question or info unnecessarily",
"conversation:context-retained":    "Agent remembers what user said earlier in the conversation",
"conversation:graceful-recovery":   "Agent recovers gracefully from user corrections or misunderstandings",
"conversation:natural-flow":        "Conversation flows naturally, not robotic or template-like",
"conversation:proactive-guidance":  "Agent proactively suggests next steps after completing a task",
```

### Rubric Dimension

```python
"conversation": {
    "dimensions": {
        "naturalness":   {"weight": 25, "labels": ["conversation:natural-flow", "conversation:no-repetition"]},
        "helpfulness":   {"weight": 35, "labels": ["conversation:proactive-guidance", "outcome:helpful-response"]},
        "resilience":    {"weight": 20, "labels": ["conversation:graceful-recovery", "conversation:context-retained"]},
        "tone":          {"weight": 20, "labels": ["conversation:tone-appropriate"]},
    }
}
```

---

## 3. Grounding Quality Assessment

The TargetStore eval revealed that **grounding rejection** is the #1 cause of agent failure in production. We need to measure it.

### New Assertion Category: `grounding:*`

```python
"grounding:no-small-talk-rejection": "Agent responses are grounded, not rejected as SMALL_TALK",
"grounding:factual-accuracy":        "Agent responses reference actual data from actions, not hallucinated info",
"grounding:source-attribution":      "Agent attributes information to the action/source that provided it",
"grounding:no-hallucination":        "Agent doesn't invent data that wasn't returned by an action",
```

### How to Measure

After each `sf agent preview` turn, parse the trace for:
- `groundingResult`: `GROUNDED` vs `NOT_GROUNDED` vs `SMALL_TALK`
- Response content vs action output content — do they match?

---

## 4. Pre-Eval Intake Questions

**This is critical.** Before the eval skill starts, it should interview the user to understand what "good" means for their specific agent. Without this, we're grading against generic structural metrics, not business requirements.

### Required Intake Questions

```
Phase 0: Intake Interview (before any eval runs)

1. BUSINESS CONTEXT
   - "What business problem does this agent solve?"
   - "Who are the end users? (customers, employees, partners)"
   - "What does a successful conversation look like?"

2. SUCCESS CRITERIA
   - "What are the top 3 things this agent MUST do well?"
   - "What must this agent NEVER do? (deal-breakers)"
   - "What's the expected resolution rate target? (e.g., 80% without human)"

3. CRITICAL SCENARIOS
   - "Give me 3-5 example conversations a real user would have"
   - "What are the most common edge cases or tricky inputs?"
   - "When should the agent escalate vs try to handle it?"

4. DOMAIN CONSTRAINTS
   - "Are there regulatory requirements? (HIPAA, PCI, financial regulations)"
   - "Are there brand voice guidelines? (formal, casual, empathetic)"
   - "Are there any actions/topics that need special gating?"

5. COMPARISON BASELINE (optional)
   - "Is there a previous version of this agent to compare against?"
   - "What's the current containment/resolution rate?"
   - "What are the most common complaints about the current agent?"
```

### How Intake Data Flows Into Eval

The intake answers generate **custom assertions** specific to the user's business:

| Intake Answer | Generated Assertion |
|--------------|-------------------|
| "Must never give medical advice" | `[safety:domain-boundaries] Does NOT provide medical diagnoses or treatment recommendations` |
| "80% resolution target" | `[outcome:task-completion] At least 4 of 5 test scenarios resolve without escalation` |
| "Formal tone for banking" | `[conversation:tone-appropriate] Responses use professional, formal language` |
| "Must verify identity first" | `[fsm:verification-gate] All account-access actions gated by verification` |
| "Common edge case: misspelled product names" | Test scenario with misspelled input + expected fuzzy match behavior |

### Suite Structure With Intake

```json
{
  "name": "Custom Eval — Acme Banking Agent",
  "intake": {
    "business_problem": "Handle balance inquiries and fund transfers for retail banking customers",
    "end_users": "Retail banking customers via messaging channel",
    "success_criteria": ["Resolve balance checks in 2 turns", "Never disclose other customers' info", "Escalate fraud reports immediately"],
    "deal_breakers": ["Providing investment advice", "Processing transfers over $10,000 without verification"],
    "regulatory": ["PCI-DSS for card data", "Reg E for electronic transfers"],
    "brand_voice": "Professional, empathetic, concise",
    "resolution_target": 0.85,
    "example_conversations": [...]
  },
  "tests": [...]
}
```

---

## 5. Key Measures for Creating Good Agents

Based on 4 eval runs and 6 real E2E deployments, here are the measures that actually predict agent quality:

### Tier 1: Must-Have (blocks deployment if failed)

| Measure | Why It Matters | Current Coverage |
|---------|---------------|-----------------|
| **Router isolation** | Without "route only" instructions, LLM answers directly and topics are never reached | `fsm:router-instructions` — covered |
| **Grounding pass rate** | Grounding rejection = dead conversation. #1 failure mode in production | Not measured today |
| **Safety compliance** | AI disclosure, scope boundaries, no impersonation — legal/brand risk | `safety:*` — well covered |
| **Action accuracy** | Calling the wrong action or wrong params = wrong results | Partially covered by `actions:*`, not by outcome testing |

### Tier 2: Quality Differentiators

| Measure | Why It Matters | Current Coverage |
|---------|---------------|-----------------|
| **Task completion rate** | The ultimate measure — did the agent do what the user wanted? | Not measured |
| **Conversation efficiency** | Too many turns = frustrated users who escalate | Not measured |
| **Context retention** | Losing context across topic switches = user repeats themselves | `chat:context-awareness` — minimal |
| **Error recovery** | Users say wrong things. Agent must recover gracefully | Not measured in conversations |

### Tier 3: Business Impact

| Measure | Why It Matters | Current Coverage |
|---------|---------------|-----------------|
| **Containment rate** | % of conversations resolved without human = cost savings | Not measured |
| **Escalation precision** | Escalating appropriately — not too early, not too late | `safety:escalation-path` exists but not scenario-tested |
| **Time to resolution** | Faster resolution = better CSAT | Not measured |
| **Cross-topic coherence** | Variables persist, context carries, transitions feel natural | Partially covered |

### Proposed Weighted Scoring

```
Agent Quality Score = weighted average of:
  30%  Task Completion (outcome:*)
  20%  Safety & Compliance (safety:*)
  15%  Grounding Quality (grounding:*)
  15%  Conversation Quality (conversation:*)
  10%  Architecture Quality (fsm:*, actions:*, logic:*)
  10%  Pipeline Reliability (deploy:*, pipeline:*)
```

This puts **business outcomes first** instead of structural correctness.

---

## 6. Implementation Roadmap

### Phase 1: Intake + Custom Assertions (Low effort, high impact)
- Add intake interview to eval CLAUDE.md Phase 0
- Generate custom assertions from intake answers
- Store intake data in suite JSON

### Phase 2: Scenario-Based Testing (Medium effort, high impact)
- Add `scenarios` field to test cases
- Execute multi-turn conversations via `sf agent preview`
- Judge action selection, parameter accuracy, outcome completion
- Parse grounding results from preview traces

### Phase 3: Conversation Quality Scoring (Medium effort, medium impact)
- Add `conversation:*` labels to taxonomy
- LLM-judge conversation transcripts for tone, flow, recovery
- Add conversation efficiency metrics (turn count, repetition)

### Phase 4: Grounding Analytics (Low effort, high impact)
- Parse `groundingResult` from preview traces
- Add `grounding:*` labels
- Flag SMALL_TALK rejections as P1 issues

### Phase 5: Business Metrics Dashboard (High effort, high impact)
- Compute containment rate from scenario results
- Track resolution rate trends across runs
- Compare against intake-defined targets
- Add business impact section to HTML report

---

## 7. Example: What a Complete Eval Looks Like

```
$ run suite custom-banking --org prod-sandbox

Phase 0: Intake Interview
  Q: What business problem does this agent solve?
  A: Handle balance inquiries and fund transfers for retail banking
  Q: What are the top 3 must-do-well items?
  A: 1) Balance checks in 2 turns  2) Never show other customers' data  3) Escalate fraud immediately
  Q: Give 3 example conversations...
  [generates 8 custom assertions from intake]

Phase 1: Load Suite — 3 tests, 35 assertions (12 standard + 8 custom + 15 scenario-based)

Phase 2: Execute Pipeline — author → discover → scaffold → deploy → test → optimize

Phase 3: Judge
  Structural:     12/12 PASS (fsm, actions, safety)
  Custom:          7/8  PASS (1 FAIL: balance check takes 4 turns not 2)
  Scenarios:      13/15 PASS (2 FAIL: fraud escalation delayed, misspelled account name not handled)
  Grounding:       5/5  PASS (all responses GROUNDED)
  Conversation:    8/8  PASS (professional tone, no repetition)

Phase 4: Report
  ┌─────────────────────────────────────────┐
  │  Banking Agent Eval — Score: 90% (A)    │
  ├─────────────────────────────────────────┤
  │  Task Completion:    87%  (13/15)       │
  │  Safety:            100%  (12/12)       │
  │  Grounding:         100%  (5/5)         │
  │  Conversation:      100%  (8/8)         │
  │  Architecture:      100%  (12/12)       │
  │  Containment:        87%  (target: 85%) │  ← meets business target
  │  Avg Turns:          3.2  (target: <4)  │  ← meets efficiency target
  ├─────────────────────────────────────────┤
  │  Issues Found:                          │
  │  P2: Balance check needs 4 turns (2)    │
  │  P2: Fraud escalation delayed 1 turn    │
  │  P3: Misspelled account name not fuzzy  │
  └─────────────────────────────────────────┘
```

---

## Summary: What to Build Next

| Priority | What | Impact | Effort |
|----------|------|--------|--------|
| **P0** | Pre-eval intake questions | Aligns eval to business goals | Low |
| **P0** | Grounding pass rate from preview traces | Catches #1 production failure mode | Low |
| **P1** | Scenario-based multi-turn testing | Measures actual task completion | Medium |
| **P1** | Custom assertion generation from intake | Makes evals business-specific | Medium |
| **P2** | Conversation quality scoring | Differentiates good from great agents | Medium |
| **P2** | Containment/resolution rate metrics | Business impact measurement | Medium |
| **P3** | Cross-run trend analysis | Track improvement over time | Low |
| **P3** | A/B comparison between agent versions | Before/after optimization impact | Low |
