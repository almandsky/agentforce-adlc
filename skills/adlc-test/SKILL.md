---
name: adlc-test
description: Smoke test Agentforce agents using sf agent preview and batch testing
allowed-tools: Bash Read Write Edit Glob Grep
argument-hint: "<org-alias> --api-name <AgentName> [--mode ad-hoc|batch]"
---

# ADLC Test

Two-mode testing for Agentforce agents: ad-hoc preview testing for development and batch Testing Center testing for regression/CI.

## Overview

This skill provides two complementary testing approaches:

- **Mode A: Ad-Hoc Preview Testing** — Uses `sf agent preview` for quick smoke tests during development. Fast iteration, immediate feedback, no test infrastructure needed.
- **Mode B: Batch Testing Center** — Uses `sf agent test` for regression suites and CI/CD. YAML test specs, automated scoring, coverage tracking.

**When to use which:**

| Scenario | Mode |
|----------|------|
| Just finished writing/editing the `.agent` file | **A** (Ad-Hoc) |
| Pre-publish validation with `--authoring-bundle` | **A** (Ad-Hoc) |
| Building a regression suite for CI/CD | **B** (Batch) |
| Measuring topic/action coverage | **B** (Batch) |
| Quick check after a targeted fix | **A** (Ad-Hoc) |
| Full agent validation before production | **B** (Batch) |

## Prerequisites

Before running any tests, ensure:

1. **Agent is published** — Run `sf agent publish authoring-bundle` first (see `adlc-deploy`)
2. **Agent is activated** — Publishing creates an **inactive** version. You MUST activate before preview/test works:
   ```bash
   sf agent activate --api-name MyAgent -o <org-alias>
   ```
   Without activation, `sf agent preview start` fails with `"No valid version available"` (HTTP 404).
3. **Action targets exist** — All flows/apex referenced by `target:` must be deployed to the org
4. **For Mode B only** — Testing Center must be enabled in the org. Check with:
   ```bash
   sf agent test list -o <org> --json
   ```
   If this returns an error, the Testing Center is not enabled. Use Mode A instead.

---

## Mode A: Ad-Hoc Preview Testing (Development)

Fast smoke testing using `sf agent preview` for rapid development iteration.

### A.1 Utterance Derivation

If no utterances are provided, derive test cases from the `.agent` file:

1. **One per non-start topic** — Based on `description:` keywords. Pick the most natural user phrasing.
2. **One that should trigger each key action** — Match the action's `description:` to a realistic user request.
3. **One off-topic utterance** — Tests guardrails (e.g., "Tell me a joke", "What's the weather?").
4. **One multi-turn pair** — If agent has topic transitions, send two related utterances to test handoff.

Example derivation:
```yaml
# Agent topics:
topic order_management:
  description: "Handle order status, tracking, shipping"
  actions:
    - get_order_status
    - track_shipment

topic returns:
  description: "Process returns, refunds, exchanges"
  actions:
    - initiate_return
    - check_refund_status

# Derived utterances:
1. "Where is my order?"             -> should route to order_management
2. "I want to return this item"     -> should route to returns
3. "Track my shipment"              -> should invoke track_shipment
4. "What's my refund status?"       -> should invoke check_refund_status
5. "Tell me a joke"                 -> should trigger guardrail
6. "Check my order" + "Actually, I want to return it" -> topic transition
```

### A.2 Preview Execution

Execute tests using `sf agent preview` programmatically.

**Important CLI flags:**
- `sf agent preview start` requires `--api-name` and `-o <org>`
- `sf agent preview send` requires `--session-id`, `--api-name`, `--utterance`, and `-o <org>`
- `sf agent preview end` requires `--session-id`, `--api-name`, and `-o <org>`
- All three commands support `--json` for machine-readable output
- For pre-publish testing: add `--authoring-bundle` to `start` and `send` (agent must have been published at least once)

```bash
# Start preview session
SESSION_ID=$(sf agent preview start \
  --api-name MyAgent \
  -o <org> --json 2>/dev/null \
  | jq -r '.result.sessionId')

# Send each test utterance
for UTTERANCE in "Where is my order?" "I want to return this" "Tell me a joke"; do
  RESPONSE=$(sf agent preview send \
    --session-id "$SESSION_ID" \
    --api-name MyAgent \
    --utterance "$UTTERANCE" \
    -o <org> --json 2>/dev/null)

  # Extract the agent's response
  echo "$RESPONSE" | jq -r '.result.messages[0].message'
done

# ALWAYS end the session when done
sf agent preview end \
  --session-id "$SESSION_ID" \
  --api-name MyAgent \
  -o <org> --json 2>/dev/null | jq '.'
```

> **CRITICAL**: Always call `sf agent preview end` when done. This triggers trace ingestion into Data Cloud STDM and frees the session. Abandoned sessions waste resources and may not produce trace data for `adlc-optimize`.

### A.3 Analyze Results

The preview produces two types of output: **inline responses** (from send) and **session artifacts** (from end).

#### Inline Response Analysis

Each `send` response contains actionable data:

```bash
# Extract response message and safety flag
echo "$RESPONSE" | jq '{
  message: .result.messages[0].message,
  type: .result.messages[0].type,
  isContentSafe: .result.messages[0].isContentSafe,
  planId: .result.messages[0].planId
}'
```

Check each response for:
- **Topic routing** — Does the response content match the expected topic?
- **Action invocation** — Did the agent ask for action inputs or return action outputs? (slot-filling indicates action was triggered)
- **Guardrail behavior** — Did off-topic utterances get redirected appropriately?
- **Content safety** — Is `isContentSafe` always `true`?

#### Session Artifacts

After `preview end`, trace files are saved locally:

```
<tracesPath>/
├── metadata.json          # Session metadata (sessionId, agentId, planIds)
├── transcript.jsonl       # Full conversation transcript (primary analysis source)
└── traces/
    └── <planId>.json      # Per-turn trace files (currently empty {} in most orgs)
```

**The transcript.jsonl file is the primary source for analysis.** Each line is a JSON object representing a user or agent message:

```bash
TRACES_PATH="<path from preview end result>"

# Parse transcript into readable format
python3 -c "
import json
with open('$TRACES_PATH/transcript.jsonl') as f:
    for line in f:
        entry = json.loads(line)
        role = entry.get('role', '?')
        text = entry.get('text', '')[:100]
        ts = entry.get('timestamp', '')
        print(f'[{ts}] {role}: {text}')
"
```

**Note:** Individual trace files under `traces/<planId>.json` are typically empty `{}` in current API versions. Detailed step-level trace data (topics, actions, LLM steps) is available through Data Cloud STDM — use the `adlc-optimize` skill for deep trace analysis.

#### Pass/Fail Classification

For each test utterance, classify the result:

| Check | Pass Criteria | Fail Indicator |
|-------|--------------|----------------|
| Topic routing | Response content matches expected topic | Response about wrong domain |
| Action invocation | Agent asks for action inputs or returns outputs | Generic conversational reply only |
| Guardrail | Off-topic utterance gets redirected | Agent attempts to answer off-topic |
| Error handling | No error messages in response | `type: "Error"` or error text |
| Content safety | `isContentSafe: true` | `isContentSafe: false` |

### A.4 Fix Loop

If issues are detected, enter a fix loop (max 3 iterations):

1. **Identify failure category**:
   - `TOPIC_NOT_MATCHED` — Topic description too vague
   - `ACTION_NOT_INVOKED` — Action guard too restrictive or description too vague
   - `WRONG_ACTION_SELECTED` — Action descriptions overlap
   - `UNGROUNDED_RESPONSE` — Missing data references
   - `LOW_SAFETY_SCORE` — Inadequate safety instructions
   - `TOOL_NOT_VISIBLE` — `available when` conditions not met

2. **Apply targeted fix**:

| Failure Type | Fix Location | Fix Strategy |
|--------------|--------------|--------------|
| TOPIC_NOT_MATCHED | `topic: description:` | Add keywords from utterance |
| ACTION_NOT_INVOKED | `available when:` or action `description:` | Relax guards or improve description |
| WRONG_ACTION | Both competing `description:` fields | Add exclusion language |
| UNGROUNDED | `instructions: ->` | Add `{!@variables.x}` references |
| LOW_SAFETY | `system: instructions:` | Add safety guidelines |

3. **Validate fix** — `sf agent validate authoring-bundle --api-name <Agent> -o <org> --json`

4. **Re-test** — New preview session with failing utterance

5. **Evaluate** — If resolved, continue; if not, iterate or proceed with warnings

---

## Mode B: Batch Testing Center (Regression/CI)

Structured test suites using `sf agent test` for repeatable, scoreable regression testing.

### B.1 Test Spec YAML Format

The Testing Center uses a specific YAML format parsed by `@salesforce/agents`. Create a test spec file:

```yaml
# Required: Display name for the test (MasterLabel) — deploy FAILS without this
name: "MyAgent Standard Tests"

# Required: Must be AGENT
subjectType: AGENT

# Required: Agent BotDefinition DeveloperName (API name)
subjectName: My_Agent_Name

testCases:
  # Topic routing test
  - utterance: "Where is my order?"
    expectedTopic: order_management
    expectedActions:
      - get_order_status
    expectedOutcome: "Agent provides order status or asks for order number"

  # Action invocation test
  - utterance: "I want to return this item"
    expectedTopic: returns
    expectedActions:
      - initiate_return

  # Guardrail test
  - utterance: "Tell me a joke"
    expectedOutcome: "Agent declines and redirects to supported topics"

  # Escalation test
  - utterance: "I want to talk to a real person"
    expectedTopic: Escalation

  # Context variable test (for authenticated agents)
  - utterance: "Show me my account"
    expectedTopic: account_details
    contextVariables:
      - name: RoutableId
        value: "<MessagingSession_ID>"

  # Multi-turn test (simulated conversation history)
  - utterance: "Now process the return"
    expectedTopic: returns
    conversationHistory:
      - role: user
        message: "I need help with order #12345"
      - role: agent
        topic: order_management
        message: "I found your order. How can I help?"
    expectedActions:
      - initiate_return
```

**Schema reference:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Test suite display name (MasterLabel). Deploy fails without this. |
| `subjectType` | Yes | Must be `AGENT` |
| `subjectName` | Yes | Agent BotDefinition DeveloperName (API name) |
| `testCases[].utterance` | Yes | User message to send |
| `testCases[].expectedTopic` | No | Expected topic name. Standard topics use `localDeveloperName` (e.g., `Escalation`). |
| `testCases[].expectedActions` | No | Flat list of action name strings. Empty `[]` means "not testing actions" (not "expect no actions"). |
| `testCases[].expectedOutcome` | No | Natural language description for LLM-as-judge scoring. Omitting causes harmless ERROR in `output_validation`. |
| `testCases[].contextVariables` | No | List of `{name, value}` pairs. Use bare names (no `$Context.` prefix). |
| `testCases[].conversationHistory` | No | Simulated prior turns. Roles must be `user` and `agent` (NOT `assistant`). |
| `testCases[].metrics` | No | List of metrics: `coherence`, `output_latency_milliseconds`. Avoid `instruction_following` (crashes UI) and `conciseness` (returns 0). |

**IMPORTANT constraints:**
- Do NOT add `apiVersion`, `kind`, `metadata`, or `settings` fields
- `expectedActions` is a **flat list of strings**, not objects
- `conversationHistory` roles must be `user` and `agent` (not `assistant`)
- For Agent Script agents, use the Level 1 **definition** name (from `topic.actions:`), not the Level 2 invocation name (from `reasoning.actions:`)

### B.2 `sf agent test` CLI Commands

The full workflow for batch testing:

```bash
# 1. Check if Testing Center is enabled
sf agent test list -o <org> --json

# 2. Create test suite from YAML spec
sf agent test create \
  --spec ./tests/agent-tests.yaml \
  --api-name MyAgentTests \
  -o <org> --json

# 3. Run tests (wait up to 10 minutes for completion)
sf agent test run \
  --api-name MyAgentTests \
  --wait 10 \
  -o <org> --json | tee /tmp/test_run.json

# 4. Get results using --job-id
JOB_ID=$(jq -r '.result.jobId // .result.aiEvaluationId' /tmp/test_run.json)
sf agent test results \
  --job-id "$JOB_ID" \
  --result-format json \
  -o <org> --json

# 5. (Optional) Re-run with verbose output for action details
sf agent test run \
  --api-name MyAgentTests \
  --wait 10 \
  --verbose \
  -o <org> --json
```

**Known bugs:**
- `--use-most-recent` flag on `sf agent test results` is **broken** (parser error as of sf CLI 2.123+). Always use `--job-id` explicitly.
- `sf agent test resume --use-most-recent` DOES work — use this if you need most-recent behavior.
- `--force-overwrite` on `sf agent test create` updates an existing test suite in place.

**Result format options:**

| Format | Flag | Use Case |
|--------|------|----------|
| Human-readable | `--result-format human` | Terminal review |
| JSON | `--result-format json` | Programmatic analysis |
| JUnit XML | `--result-format junit` | CI/CD integration |
| TAP | `--result-format tap` | TAP consumers |

### B.3 Analyze Results

Parse the JSON results to identify failures:

```bash
# Extract pass/fail summary
jq '{
  total: (.result.testCases | length),
  passed: [.result.testCases[] | select(.status == "PASS")] | length,
  failed: [.result.testCases[] | select(.status == "FAIL")] | length,
  errors: [.result.testCases[] | select(.status == "ERROR")] | length
}' /tmp/test_results.json

# Show failures with details
jq '.result.testCases[] | select(.status != "PASS") | {
  utterance: .utterance,
  status: .status,
  expectedTopic: .expectedTopic,
  actualTopic: .generatedData.topic,
  expectedActions: .expectedActions,
  actualActions: .generatedData.invokedActions
}' /tmp/test_results.json
```

**Scoring dimensions:**

| Dimension | What It Tests | Pass Criteria |
|-----------|---------------|---------------|
| `topic_sequence_match` | Correct topic routing | Actual topic = expected topic |
| `action_sequence_match` | Correct action invocation | Expected actions are subset of actual |
| `output_validation` | Response quality (LLM-as-judge) | Score >= threshold (0.7 default) |
| `coherence` | Response coherence | Score >= 3 (out of 5) |

### B.4 Fix Loop

Same as Mode A fix loop (section A.4), but after fixing:

1. Edit the `.agent` file
2. Republish: `sf agent publish authoring-bundle --api-name <Agent> -o <org> --json`
3. Reactivate: `sf agent activate --api-name <Agent> -o <org>`
4. Re-run: `sf agent test run --api-name <TestName> --wait 10 -o <org> --json`

> **Note**: After republishing, promoted topic `developerName` hashes may change. If tests suddenly fail on `topic_sequence_match` after a republish, re-discover the topic names:
> ```bash
> sf data query --query "SELECT DeveloperName, MasterLabel FROM GenAiPluginDefinition WHERE DeveloperName LIKE '%_<15-char-planner-id>'" -o <org> --json
> ```

### B.5 Coverage Report

After running tests, assess coverage across these 8 dimensions:

```
Coverage Report
═══════════════════════════════════════════

Topic Coverage:    4/5 (80%)    — % topics with test cases
Action Coverage:   8/12 (66.7%) — % actions tested
Phrasing Diversity: 1.2/topic  — unique phrasings per topic (target: 3+)
Guardrail Coverage: 3/5 (60%)  — off-topic + boundary tests
Escalation Tests:  1/1 (100%)  — escalation path verified
Context Var Tests: 0/2 (0%)    — context variable injection tested
Multi-turn Tests:  1/3 (33.3%) — conversation history scenarios
Outcome Validation: 6/8 (75%) — expectedOutcome assertions

Overall: 62.5%
Target:  90%+ for production readiness
```

**Coverage formulas:**
```
Topic Coverage   = (Topics with test cases / Total non-start topics) x 100
Action Coverage  = (Actions with test cases / Total actions) x 100
Phrasing Score   = Unique phrasings / Total topics (target: 3+ per topic for production)
Guardrail Score  = Guardrail tests / (off-topic + boundary + injection + abuse) tests needed
```

**Recommendations to reach 90%:**
- Add at least 3 phrasing variations per topic
- Add off-topic, injection, and abuse guardrail tests
- Test every action at least once
- Add `contextVariables` tests for agents with session context
- Add `conversationHistory` tests for multi-turn flows

---

## Auto-Generating Test Specs from .agent Files

Derive test specs directly from the `.agent` file structure:

1. **One `testCase` per topic** — Utterance derived from topic `description:` keywords
2. **One `testCase` per action** — Trigger the action's primary use case from its `description:`
3. **One guardrail test** — Off-topic utterance
4. **One escalation test** — "I want to talk to a human"
5. **`expectedTopic`** from topic name, **`expectedActions`** from action definition names

Example: Given this `.agent` excerpt:

```yaml
topic order_management:
  description: "Handle order queries, status tracking, shipping updates"
  actions:
    get_order_status:
      description: "Look up order status by order number"
      target: "flow://Get_Order_Status"
    track_shipment:
      description: "Track package shipping status"
      target: "flow://Track_Shipment"

topic returns:
  description: "Process product returns and refund requests"
  actions:
    initiate_return:
      description: "Start a product return process"
      target: "flow://Initiate_Return"
```

Generate this test spec:

```yaml
name: "MyAgent Auto-Generated Tests"
subjectType: AGENT
subjectName: MyAgent

testCases:
  # Topic: order_management (from description keywords)
  - utterance: "Where is my order?"
    expectedTopic: order_management

  - utterance: "Can you track my shipment?"
    expectedTopic: order_management

  # Action: get_order_status (from action description)
  - utterance: "Look up the status of order #12345"
    expectedTopic: order_management
    expectedActions:
      - get_order_status

  # Action: track_shipment
  - utterance: "Where is my package?"
    expectedTopic: order_management
    expectedActions:
      - track_shipment

  # Topic: returns (from description keywords)
  - utterance: "I want to return a product"
    expectedTopic: returns

  # Action: initiate_return
  - utterance: "Start a return for my recent purchase"
    expectedTopic: returns
    expectedActions:
      - initiate_return

  # Guardrail: off-topic
  - utterance: "Tell me a joke"
    expectedOutcome: "Agent declines and redirects to supported topics"

  # Escalation
  - utterance: "I want to talk to a real person"
    expectedTopic: Escalation
```

---

## Test Spec Templates

Pre-built templates in `assets/` for common patterns:

| Template | Description | File |
|----------|-------------|------|
| Basic | Minimal 5-test template (topic + action + outcome + escalation) | `assets/basic-test-spec.yaml` |
| Standard | 8-test template with all field types including context vars and conversation history | `assets/standard-test-spec.yaml` |
| Guardrail | Off-topic, injection, abuse, and session management tests | `assets/guardrail-test-spec.yaml` |

Read the template closest to your needs, then customize with your agent's topics, actions, and utterances.

---

## Test Report Format

### Summary Report (Ad-Hoc)
```
Agentforce Agent Test Report (Ad-Hoc)
═══════════════════════════════════════════

Agent: OrderManagementAgent
Org: production
Test Cases: 6
Duration: 45.2s

Results:
  Topic Routing:     5/6 passed (83.3%)
  Action Invocation: 4/6 passed (66.7%)
  Guardrail:         1/1 passed (100%)
  Content Safety:    6/6 passed (100%)

Overall: 83.3%
Status: PASSED WITH WARNINGS
```

### Summary Report (Batch)
```
Agentforce Agent Test Report (Batch - Testing Center)
═══════════════════════════════════════════

Agent: OrderManagementAgent
Test Suite: OrderMgmt_Standard_Tests
Org: production
Test Cases: 12

Results:
  topic_sequence_match:  10/12 (83.3%)
  action_sequence_match:  9/12 (75.0%)
  output_validation:      8/10 (80.0%)

Coverage:
  Topics:  4/5 (80%)
  Actions: 8/12 (66.7%)

Overall: 79.4%
Status: NEEDS IMPROVEMENT (target: 90%)
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `No valid version available` (404) | Agent not activated after publish | Run `sf agent activate --api-name MyAgent -o <org>` |
| `sf agent test list` returns error | Testing Center not enabled in org | Use Mode A (ad-hoc preview) instead |
| `--use-most-recent` parser error | Known bug in sf CLI 2.123+ | Use `--job-id` explicitly |
| Session timeout | Long-running tests | Split into smaller batches |
| Trace not found | CLI version issue | Update to sf CLI 2.121.7+ |
| Context variables missing | Preview limitation | Use Mode B with `contextVariables` field |
| `instruction_following` metric crashes UI | Platform bug | Remove from metrics list; use `coherence` instead |
| `conciseness` metric returns 0 | Platform bug | Skip this metric entirely |
| Topic hash changed after republish | Expected behavior | Re-discover topic names via SOQL query |
| `expectedActions` test passes but action didn't run | Agent Script action types differ | Use Level 1 definition name; check with `--verbose` |

### Debug Mode

Enable detailed logging for ad-hoc tests:

```bash
export ADLC_DEBUG=true
export ADLC_LOG_LEVEL=DEBUG

python3 scripts/test.py \
  -o myorg \
  --api-name MyAgent \
  --debug --verbose
```

For batch tests, use `--verbose` flag:

```bash
sf agent test run --api-name MyTests --wait 10 --verbose -o <org> --json
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Agent Testing
on:
  pull_request:
    paths:
      - 'force-app/**/*.agent'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Salesforce CLI
        run: npm install -g @salesforce/cli

      - name: Authenticate org
        run: |
          echo "${{ secrets.SFDX_AUTH_URL }}" > auth.txt
          sf org login sfdx-url --sfdx-url-file auth.txt --alias testorg

      - name: Run batch tests
        run: |
          sf agent test run \
            --api-name ${{ vars.TEST_SUITE_NAME }} \
            --wait 10 \
            --result-format junit \
            -o testorg --json > test-results.json

      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: test-results.json
```

---

## Best Practices

### Test Strategy

1. **Start with Mode A** — Quick smoke tests during development
2. **Build Mode B suite** — Create a comprehensive test spec once agent stabilizes
3. **Test all topics** — At least one utterance per topic
4. **Test all actions** — At least one utterance per action
5. **Add guardrails** — Off-topic, injection, abuse tests
6. **Add phrasing diversity** — 3+ variations per topic for production
7. **Always end sessions** — Call `sf agent preview end` after every ad-hoc test

### Test Maintenance

- Version test specs with agent source code
- Update `expectedTopic` names after republishing (hashes change)
- Review `expectedOutcome` descriptions when agent behavior evolves
- Re-run coverage analysis after adding new topics or actions
