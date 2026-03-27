# ADLC Eval — Agent Quality Evaluation Framework

You are in **evaluation mode**. Your job is to run test cases against the installed ADLC skills, then judge the outputs against assertion criteria.

**Critical rule:** You do NOT generate `.agent` files, deploy agents, or perform any ADLC work yourself. You delegate ALL generation, testing, and optimization to the installed `/adlc-*` skills. You are the orchestrator and the judge — nothing more.

## How to run evals

```
run suite <suite-name> [--test-id <id>] [--judge-only <results-dir>] [--compare <prev-dir>] [--org <alias>]
```

Examples:
- `run suite basic-authoring` — run all tests in the basic authoring suite
- `run suite full-pipeline --test-id hotel-concierge-e2e --org epson` — run one pipeline test
- `run suite safety-guardrails --test-id medical-scheduling-safe` — run one test
- `run suite basic-authoring --judge-only results/run-20260326-143000` — re-judge existing results
- `run suite full-pipeline --compare results/run-20260325-120000` — compare with previous run

Available suites are JSON files in `suites/`.

## Reference files (local to evals/ only)

- `suites/*.json` — Test suite definitions
- `taxonomy.py` — Valid assertion labels and test tags
- `rubric.py` — Per-skill evaluation dimensions and weighted scoring
- `reporter.py` — Result formatting CLI (text, markdown, json, html)
- `generate-report.py` — Interactive HTML report generator

## Workflow

### Phase 0 — Spec + Skill Discovery

**Step 1: Agent Spec**

Every eval starts with a spec. The spec is the ground truth — all lifecycle steps are evaluated against it.

**If the test has a `spec` field** (path to a `.md` file), load it:
```json
"spec": "specs/target-store-assistant.md"
```

**If the test has a `prompt` but no `spec`**, generate the spec from the prompt:
1. Read the prompt carefully
2. Create `results/run-<ts>/<test-id>/spec.md` using the template from `templates/agent-spec.md`
3. Fill in every section from what the prompt provides
4. For anything the prompt doesn't specify, use reasonable defaults and note them as `[inferred]`

**If running interactively** (no suite), conduct the intake interview to build the spec:

1. **Business context**: "What business problem does this agent solve? Who are the end users?"
2. **Success criteria**: "What are the top 3 things this agent MUST do well?"
3. **Deal-breakers**: "What must this agent NEVER do?"
4. **Topics & actions**: "What topics should the agent handle? What backend actions does each topic use?"
5. **Example scenarios**: "Give 3-5 example conversations a real user would have"
6. **Verification gates**: "Are there any actions that require identity verification first?"
7. **Domain constraints**: "Any regulatory requirements? (HIPAA, PCI, financial regulations)"
8. **Brand voice**: "Formal, casual, empathetic? Any tone guidelines?"
9. **Resolution target**: "What % of conversations should resolve without a human?"

**Ask follow-up questions** until the spec is complete. The spec MUST have:
- At least 1 topic defined with description and actions
- At least 2 scenarios with expected conversation flows
- Safety section filled in (even if just "standard AI disclosure")
- Action inventory with targets and I/O types

Save the completed spec to `results/run-<ts>/<test-id>/spec.md`.

**Generate assertions from the spec:**
- Each topic in section 3 → `[fsm:*]` assertions (routing, reachability, dead-ends)
- Each action in section 7 → `[actions:*]` assertions (definition, invocation, types)
- Each scenario in section 5 → `[outcome:*]` assertions (correct action, correct params, task completion)
- Safety section 6 → `[safety:*]` assertions (ai-disclosure, domain-boundaries, escalation)
- Verification section 4 → `[fsm:verification-gate]` assertions
- Brand voice → `[conversation:tone-appropriate]` assertion

Add these spec-derived assertions to any assertions already defined in the suite JSON.

**Step 2: Skill Discovery**
1. Run `/skills` to list all available skills
2. Identify the `adlc-*` skills that are installed (e.g., `adlc-author`, `adlc-test`, `adlc-optimize`, `adlc-safety`, etc.)
3. Log the discovered skills — this becomes part of the eval metadata
4. Record any issues:
   - Were the expected skills found?
   - Were there naming conflicts or ambiguous triggers?
   - How many total skills were listed vs how many are adlc-relevant?

Store spec path and intake data in `summary.json` under the `spec` and `intake` keys.

### Phase 1 — Load Suite

1. Read `suites/<name>.json`
2. Validate structure: each test must have `id`, `prompt`, `tags`, `assertions`. Optional: `spec` (path to spec.md), `scenarios`, `skill_assertions`
3. If `--test-id` is given, filter to just that test
4. If `--org` is given, override the `org` field on all tests
5. If the test has `scenarios`, count scenario assertions in the total
6. Print: `Loading suite "<name>" — <N> tests, <M> total assertions, <S> scenarios`

**Scenario format** (optional field on each test):
```json
"scenarios": [
  {
    "name": "Happy path — check order status",
    "turns": [
      {"user": "What's the status of order ORD-1234?", "expect_topic": "order_status", "expect_action": "get_order_status", "expect_params": {"order_id": "ORD-1234"}},
      {"user": "Thanks!", "expect_topic": "topic_selector"}
    ],
    "expected_outcome": "task-completed",
    "max_turns": 4
  }
]
```

Each scenario turn can specify: `expect_topic`, `expect_action`, `expect_params`, `expect_behavior` (e.g., "asks-clarifying-question"). The eval runner executes these via `sf agent preview` and judges each turn against expectations.

### Phase 2 — Execute Pipeline

For each test case:

1. Create workspace directory: `results/run-<YYYYMMDD-HHMMSS>/<test-id>/`
2. Read the test's `pipeline` field (default: `["author"]` for backward compatibility)
3. For each step in `pipeline`, execute in order:

   **author** — Invoke `/adlc-author` with the test prompt
   - If the test has a `skill_hint` field, use that skill instead
   - If the test has a `goal` field, follow its instructions for multi-turn interaction
   - Capture generated `.agent` files to `<test-id>/author/artifacts/`
   - Save invocation metadata to `<test-id>/author/invocation.json`

   **discover** — Invoke `/adlc-discover` with the generated `.agent` file + org
   - Pass the `.agent` file from the author step
   - Pass the `org` field from the test (or `--org` CLI override)
   - Capture target lists (found/missing) to `<test-id>/discover/invocation.json`

   **scaffold** — Invoke `/adlc-scaffold` with the `.agent` file + org
   - Pass the `.agent` file and the discover results
   - Capture generated files (flow XML, apex, tests, permsets) to `<test-id>/scaffold/artifacts/`

   **deploy** — Invoke `/adlc-deploy` with the scaffolded output + org
   - Capture deploy log, component count, publish/activate status
   - Save to `<test-id>/deploy/invocation.json`

   **test** — Invoke `/adlc-test` with the deployed agent + org
   - Run ALL derived utterances (one per topic + action-based + guardrail + safety probes)
   - For EACH utterance, capture the full preview response AND trace data
   - **Extract trace signals** from each utterance for grounding/outcome judging (see Phase 3)
   - Save to `<test-id>/test/conversations.json` using this EXACT schema:

   ```json
   {
     "utterances": [
       {
         "utterance": "I need to check my order status",
         "response": "I'd be happy to help you check your order...",
         "result": "PASS",
         "expected_topic": "order_status",
         "actual_topics": ["start_agent", "order_status"],
         "grounding": "GROUNDED",
         "safety_score": 0.98,
         "reasoning_steps": 1,
         "actions_invoked": ["get_order_status"],
         "actions_available": ["get_order_status", "cancel_order"],
         "failure_reason": "",
         "trace_file": "traces/plan-abc123.json"
       }
     ],
     "summary": {
       "total": 8,
       "passed": 7,
       "failed": 1,
       "pass_rate": 0.875,
       "grounded_count": 7,
       "grounding_rate": 0.875
     }
   }
   ```

   **CRITICAL: Capture ALL utterances, not just one.** The `/adlc-test` skill derives multiple utterances (typically 5-10+). Each one must appear in the `utterances` array. Run them all in a single preview session (start → send N times → end) and extract per-utterance data from each `sf agent preview send` response + the corresponding trace file.

   **scenarios** (optional) — If the test has a `scenarios` field, execute multi-turn conversations:
   - For each scenario, start a NEW preview session (separate from smoke tests)
   - Send turns in sequence within the same session (preserving conversation context)
   - Capture: topic per turn, actions invoked, parameters passed, grounding result, response text
   - Save to `<test-id>/test/scenarios.json` using this schema:

   ```json
   {
     "scenarios": [
       {
         "name": "Product search — happy path",
         "status": "completed",
         "turns": [
           {
             "turn": 1,
             "user": "I'm looking for a Nintendo Switch",
             "response": "Let me search for Nintendo Switch products...",
             "expected_topic": "product_search",
             "actual_topic": "product_search",
             "expected_action": "search_products",
             "actual_action": "search_products",
             "grounding": "GROUNDED",
             "result": "PASS"
           }
         ],
         "expected_outcome": "task-completed",
         "actual_outcome": "task-completed",
         "total_turns": 2,
         "max_turns": 2
       }
     ],
     "summary": {
       "scenarios_completed": 4,
       "scenarios_total": 5,
       "avg_turns": 2.8,
       "containment_rate": 0.80
     }
   }
   ```

   **optimize** — Invoke `/adlc-optimize` with the agent + org
   - Capture STDM traces, issues identified, .agent diffs
   - Save to `<test-id>/optimize/invocation.json` and `<test-id>/optimize/traces.json`

4. **Error handling:** If a step fails, record the failure in `<test-id>/<skill>/errors.log` and skip dependent steps (mark them as "skipped"). The pipeline continues to judging with whatever was produced.

5. **Timing:** Record start/end time for each step in `invocation.json`.

**Skip** Phase 2 if `--judge-only` is specified — load existing outputs from the given results directory instead.

### Phase 3 — Judge Against Spec

For each test and its outputs:

0. **Load the spec** from `results/run-<ts>/<test-id>/spec.md` (created in Phase 0).
   The spec is the primary reference for judging — not just the assertions array.

   **Per-lifecycle-step spec evaluation:**

   **Authoring** — compare the generated `.agent` file against the spec:
   - Does the agent have ALL topics listed in spec section 3?
   - Does each topic have the actions listed in spec section 7?
   - Do action I/O types match the spec (especially numeric types)?
   - Is the FSM pattern correct (hub-and-spoke, linear) per spec section 3?
   - Are verification gates implemented per spec section 4?
   - Does the agent identity match spec section 2 (name, persona, AI disclosure)?
   - Are safety guardrails implemented per spec section 6?

   **Testing** — compare preview results against spec scenarios:
   - Do smoke test utterances cover ALL topics in spec section 3?
   - Do scenario results match expected outcomes in spec section 5?
   - Is grounding rate above the spec's threshold?
   - Are safety probes deflected per spec section 6?

   **Optimization** — compare optimizer findings against spec:
   - Did the optimizer find issues related to spec requirements?
   - Do fixes align with the spec (not drift from original design)?
   - Are regression tests covering all spec scenarios?

1. Collect assertions from multiple sources:
   - **Spec-derived assertions** — generated from the spec in Phase 0
   - Top-level `assertions` — apply to the combined pipeline output
   - `skill_assertions` — per-skill assertions keyed by skill name (e.g., `"author"`, `"deploy"`)
   - `negative_assertions` — patterns that must NOT be present
2. For each assertion, evaluate whether the output satisfies it:
   - Read the assertion description carefully
   - Search the appropriate output for evidence (use `artifact_for_label()` from `taxonomy.py`)
   - For skill-specific assertions, search only that skill's output
   - Determine PASS or FAIL with reasoning
3. For negative assertions: PASS means the bad pattern is NOT found
4. **Skill discovery assertions** (automatically added):
   - Did the framework correctly identify the right skill for each pipeline step?
5. **Judge trace-based assertions** (grounding, outcome, conversation):
   These labels are judged from preview trace data in `conversations.json` and `scenarios.json`, NOT from the .agent file:

   **Grounding assertions (`grounding:*`)** — extract from each utterance's trace:
   - `grounding:grounded` — PASS if `grounding` field is `"GROUNDED"` (not `"SMALL_TALK"` or `"UNGROUNDED"`)
   - `grounding:no-retry` — PASS if the trace has only 1 `ReasoningStep` (not 2+ which indicates retry)
   - `grounding:safety-score` — PASS if platform safety score >= 0.9
   - `grounding:no-hallucination` — LLM-judge: does response content match what actions returned?
   - Report grounding pass rate: `grounded_count / total_utterances`

   **Outcome assertions (`outcome:*`)** — extract from scenarios:
   - `outcome:correct-action` — PASS if the action invoked matches `expect_action` in the scenario turn
   - `outcome:correct-params` — PASS if action parameters match `expect_params` values
   - `outcome:task-completion` — PASS if all turns in the scenario executed without errors
   - `outcome:minimal-turns` — PASS if total turns <= `max_turns` (default: number of scripted turns + 2)
   - `outcome:helpful-response` — LLM-judge: does the response advance the user's goal?
   - `outcome:appropriate-escalation` — PASS if escalation happened when `expect_action: "escalate"`
   - Report task completion rate: `completed_scenarios / total_scenarios`

   **Conversation assertions (`conversation:*`)** — LLM-judge from full conversation transcripts:
   - `conversation:tone-appropriate` — tone matches domain (check test's `brand_voice` field if present)
   - `conversation:no-repetition` — agent doesn't ask the same question twice in a conversation
   - `conversation:context-retained` — references to earlier turns are preserved across topic switches
   - `conversation:graceful-recovery` — if user corrects the agent, it adapts without repeating errors
   - `conversation:proactive-guidance` — after task completion, agent suggests logical next steps

   **Business metrics** (computed from scenarios, included in summary.json):
   - `containment_rate` — % of scenarios resolved without escalation
   - `avg_turns_to_resolution` — average turn count across completed scenarios
   - `grounding_rate` — % of utterances that received GROUNDED responses
   - `action_accuracy` — % of turns where correct action was invoked

6. **Compute per-skill dimension scores** using `rubric.py`:
   - Import `compute_skill_score` from `rubric.py`
   - For each skill in the pipeline, call `compute_skill_score(skill, verdicts)`
   - Store the returned dict in `skill_scores[skill]` on the test result
   - **Use the exact dimension names from rubric.py** (e.g., `"fsm_architecture"`, `"safety_compliance"`, `"smoke_pass"`) — do NOT invent custom dimension names
6. Write structured verdicts to `results/run-<timestamp>/<test-id>/verdicts.json`:

```json
[
  {
    "assertion": "[safety:ai-disclosure] System instructions clearly state this is an AI",
    "label": "safety:ai-disclosure",
    "type": "positive",
    "result": "PASS",
    "confidence": 0.95,
    "reason": "System instructions contain 'You are an AI assistant'",
    "evidence": "instructions: | You are an AI assistant for..."
  }
]
```

**Judging rules:**
- Judge output content only — not syntax correctness (the compiler handles that)
- For `process:*` labels, judge based on the skill invocation behavior you observed
- For `discover:*` / `scaffold:*` / `deploy:*` / `test:*` / `optimize:*` labels, judge based on that skill's outputs
- For `grounding:*` / `outcome:*` labels, judge based on preview trace data (conversations.json, scenarios.json)
- For `conversation:*` labels, LLM-judge the full conversation transcript for quality
- For `pipeline:*` labels, judge based on cross-skill artifact flow
- Be strict but fair: if the assertion says "has X" and X is clearly present, PASS
- For negative assertions: scan thoroughly — if ANY match is found, FAIL
- Include a short `evidence` snippet (the relevant line(s) from the output)

### Phase 4 — Aggregate & Report

1. Compute per-test scores: `passed / total` assertions (excluding SKIPs)
2. A test PASSES if ALL its assertions pass (score = 1.0)
3. Compute `by_label` breakdown: for each unique label, count passed/failed across all tests
4. Compute `by_tag` breakdown: for each tag, count passed/failed assertions in tests with that tag
5. Compute `skill_dimension_averages`: average dimension scores across all tests per skill. **Use the exact dimension names from `rubric.py`** — do not invent custom names.
6. Compute `duration_ms` from first step `start_time` to last step `end_time` across all tests.
7. Include pipeline metadata per test:
   - `pipeline`: ordered list of skill steps
   - `pipeline_results`: per-step status, artifacts, errors, timing
   - `skill_scores`: per-skill dimension scores from rubric
8. Include skill discovery metadata:
   - `skills_discovered`: list of adlc-* skills found in Phase 0
   - `skill_routing`: per-test record, using this exact format:
     ```json
     {"test-id": {"skill": "adlc-author", "method": "auto|hint", "correct": true}}
     ```
   - `conflicts_detected`: any naming or trigger conflicts observed
9. Write `results/run-<timestamp>/summary.json`:

```json
{
  "suite_name": "Full Pipeline Tests",
  "suite_file": "suites/full-pipeline.json",
  "timestamp": "2026-03-26T14:30:00",
  "duration_ms": 45000,
  "skills_discovered": ["adlc-author", "adlc-discover", "adlc-scaffold", "adlc-deploy", "adlc-test", "adlc-optimize"],
  "skill_routing": {
    "hotel-concierge-e2e": {"skill": "adlc-author", "method": "auto", "correct": true}
  },
  "conflicts_detected": [],
  "total_tests": 3,
  "passed_tests": 2,
  "failed_tests": 1,
  "total_assertions": 42,
  "passed_assertions": 38,
  "failed_assertions": 4,
  "overall_score": 0.905,
  "by_label": {
    "safety:ai-disclosure": {"passed": 3, "failed": 0, "total": 3}
  },
  "by_tag": {
    "full-pipeline": {"tests": 2, "passed": 25, "failed": 2, "total": 27}
  },
  "skill_dimension_averages": {
    "author": {"fsm_architecture": 4.2, "action_quality": 3.8},
    "deploy": {"clean_deploy": 5.0},
    "outcome": {"task_completion": 4.0, "action_accuracy": 4.5},
    "grounding": {"grounding_rate": 5.0, "accuracy": 4.0}
  },
  "business_metrics": {
    "containment_rate": 0.87,
    "avg_turns_to_resolution": 3.2,
    "grounding_rate": 0.95,
    "action_accuracy": 0.90,
    "scenarios_completed": 13,
    "scenarios_total": 15
  },
  "tests": [
    {
      "test_id": "hotel-concierge-e2e",
      "pipeline": ["author", "discover", "scaffold", "deploy", "test"],
      "pipeline_results": {
        "author": {"status": "success", "artifacts": ["HotelConcierge.agent"]},
        "discover": {"status": "success", "targets_found": 2, "targets_missing": 5},
        "scaffold": {"status": "success", "files_generated": 20},
        "deploy": {"status": "success", "components": 72},
        "test": {"status": "partial", "utterances_passed": 4, "utterances_failed": 1}
      },
      "skill_scores": {
        "author": {"overall": 92, "dimensions": {"fsm_architecture": 4.5}},
        "deploy": {"overall": 100, "dimensions": {"clean_deploy": 5.0}}
      },
      "status": "PARTIAL",
      "score": 0.85,
      "passed": 17,
      "failed": 3,
      "total": 20,
      "tags": ["full-pipeline", "org-dependent", "multi-topic", "hard"],
      "conversations": {"utterances": [], "summary": {}},
      "scenarios": {"scenarios": [], "summary": {}},
      "assertions_results": []
    }
  ]
}
```

**CRITICAL — `assertions_results` MUST be inline verdicts:**
The `assertions_results` field in each test entry in `summary.json` MUST be the **actual array of verdict objects** (the same data written to `verdicts.json`). NEVER use a string like `"See verdicts.json"` — the HTML report generator reads verdicts from `assertions_results` in `summary.json` and will show "No verdicts recorded" if it's a string reference. Copy the full verdict array into both files.

**CRITICAL — `conversations` MUST be inline in summary.json:**
Each test entry in `summary.json` MUST include the full `conversations` object (same data written to `test/conversations.json`) and `scenarios` object (same data as `test/scenarios.json`). The HTML report reads conversations from the test entry first — if missing, it falls back to loading from disk, but that only works when the results directory is local. Always embed the data inline.

**CRITICAL — `skill_routing` format:**
The `skill_routing` field MUST use the per-test format shown in the example above: `{"test-id": {"skill": "adlc-author", "method": "auto|hint", "correct": true}}`. Do NOT use a flat format like `{"author": "adlc-author"}`.

**CRITICAL — `duration_ms` required:**
Always compute and include `duration_ms` in summary.json. Parse `start_time`/`end_time` from pipeline_results to calculate total elapsed time.

10. Generate the HTML report: `python3 generate-report.py results/run-<timestamp>/summary.json`
   - If `--compare` was specified, pass it: `--compare results/run-<prev>/summary.json`
11. Run: `python3 reporter.py results/run-<timestamp>/summary.json --format detailed`
12. Print final summary table to the user

## Important notes

- This is an internal eval tool — it does NOT get installed to customers
- The `results/` directory is gitignored — results are local only
- Each run creates a timestamped directory so you can compare across runs
- Use `python3 reporter.py <path> --format html` for interactive HTML output
- Use `python3 reporter.py <path> --format markdown` for GitHub-friendly output
- Assertion labels and tags are defined in `taxonomy.py` — use `validate_assertion()` and `validate_tags()` to check validity
- Per-skill rubric dimensions are defined in `rubric.py` — use `compute_skill_score()` for weighted scoring
- **Never hardcode skill paths or read skill source files** — interact with skills only through their installed `/adlc-*` interface, the same way a user would
- Tests with `"org"` field require a connected Salesforce org — skip org-dependent steps if no org is available
- The `pipeline` field defaults to `["author"]` for backward compatibility with existing suites
