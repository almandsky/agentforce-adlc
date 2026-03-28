<!-- Parent: adlc-author/SKILL.md -->
# Preview Smoke Test Loop (Phase 3.5)

> Rapid feedback on `.agent` files before publish -- no CWC patch, no activate, no cross-skill delegation.

---

## 1. Overview

**Purpose**: After Phase 3 validation passes, run 3-5 smoke test utterances against the agent using `sf agent preview --authoring-bundle` to catch topic routing, action invocation, and grounding issues *before* the formal publish/activate/test cycle.

**Why this matters**: The `--authoring-bundle` flag compiles the `.agent` file server-side **without publishing** -- no CustomerWebClient patch, no activation step. This enables ~15s iteration cycles (vs ~90s for publish+activate), letting Claude Code fix issues in a tight inner loop.

**API used**: `/einstein/ai-agent/v1.1/preview/` endpoint (separate from the Runtime API used in testing). Traces are saved locally by the `sf` CLI.

**Trace location**: `.sfdx/agents/{BundleName}/sessions/{sessionId}/traces/{planId}.json`

---

## 2. Prerequisites

| Requirement | How to Check | Why |
|---|---|---|
| Agent published **at least once** | `sf agent publish authoring-bundle --api-name X -o Org --json` returns success OR agent is already visible in Setup | Preview requires a baseline `GenAiPlannerDefinition` to exist. First publish creates it. Subsequent `--authoring-bundle` compiles against the local `.agent` file without re-publishing. |
| sf CLI >= 2.121.7 | `sf --version` | Earlier versions lack `--authoring-bundle` flag and `preview send` subcommand. |
| Valid Einstein Agent User in target org | `sf data query -q "SELECT Username FROM User WHERE Profile.Name = 'Einstein Agent User' AND IsActive = true" -o Org --json` | The `default_agent_user` in `config:` must resolve to a real user. |
| Agent type matches channel | Check `agent_type:` in `.agent` | `AgentforceServiceAgent` needs `connection messaging:` block; `AgentforceEmployeeAgent` does not. |
| All action targets deployed to org | `sf project deploy start --metadata Flow:MyFlow -o Org` for each target | Preview calls live targets. Missing targets cause `ACTION_ERROR`. |

---

## 3. Workflow

### 3.1 Start Preview Session

```bash
SESSION_ID=$(sf agent preview start \
  --authoring-bundle MyAgent \
  -o TargetOrg --json 2>/dev/null \
  | jq -r '.result.sessionId')

echo "Session: $SESSION_ID"
```

The `--authoring-bundle <BundleName>` flag tells the server to compile the local `.agent` file instead of using the last-published version. This is the key to the ~15s iteration cycle. **The same flag must appear on all three subcommands** (`start`, `send`, `end`).

### 3.2 Send Utterances

```bash
for UTT in \
  "What is my order status?" \
  "I want to return an item" \
  "Tell me a joke"
do
  echo "--- Sending: $UTT ---"
  RESPONSE=$(sf agent preview send \
    --session-id "$SESSION_ID" \
    --authoring-bundle MyAgent \
    --utterance "$UTT" \
    -o TargetOrg --json 2>/dev/null)

  echo "$RESPONSE" | jq '{
    message: .result.messages[0].message,
    type: .result.messages[0].type,
    planId: .result.messages[0].planId,
    isContentSafe: .result.messages[0].isContentSafe
  }'
done
```

### 3.3 End Session and Save Traces

```bash
TRACES=$(sf agent preview end \
  --session-id "$SESSION_ID" \
  --authoring-bundle MyAgent \
  -o TargetOrg --json 2>/dev/null)

TRACES_PATH=$(echo "$TRACES" | jq -r '.result.tracesPath')
echo "Traces at: $TRACES_PATH"
```

### 3.4 Read Trace Files

Each turn produces a trace JSON file named by `planId`:

```bash
for TRACE in "$TRACES_PATH"/traces/*.json; do
  echo "=== $(basename "$TRACE") ==="
  jq '.' "$TRACE"
done
```

---

## 4. Trace Analysis Checks

Run these 6 checks against each trace file to classify pass/fail.

### Check 1: Topic Routing

Did the correct topic handle the utterance?

```bash
# Root-level topic field
jq -r '.topic' "$TRACE"
# Detailed: which agent/topic was entered
jq -r '.plan[] | select(.type == "NodeEntryStateStep") | .data.agent_name' "$TRACE"
```

**Pass**: Topic name matches the expected topic for the utterance.
**Fail**: Wrong topic or no `NodeEntryStateStep` found.

### Check 2: Action Invocation

Did the expected action fire?

```bash
# Which actions were available for this reasoning iteration
jq -r '.plan[] | select(.type == "BeforeReasoningIterationStep") | .data.action_names[]' "$TRACE"
```

**Pass**: Expected action name appears in the list.
**Fail**: Action not listed or wrong action invoked.

### Check 3: Grounding

Did the response pass grounding assessment?

```bash
# Check grounding category and reason
jq -r '.plan[] | select(.type == "ReasoningStep") | {category: .category, reason: .reason}' "$TRACE"
```

**Pass**: `.category` is `"GROUNDED"`.
**Fail**: `.category` is `"UNGROUNDED"` -- read `.reason` for details.

**UNGROUNDED retry detection:** When grounding returns UNGROUNDED, the system retries by injecting an error message and running a second LLM+Reasoning cycle. You'll see 2+ `ReasoningStep` entries:
```bash
jq '[.plan[] | select(.type == "ReasoningStep")] | length' "$TRACE"
# 1 = normal, 2+ = UNGROUNDED retry happened
```

### Check 4: Safety Score

Did the content safety check pass?

```bash
jq -r '.plan[] | select(.type == "PlannerResponseStep") | .safetyScore.safetyScore.safety_score' "$TRACE"
```

**Pass**: Score >= 0.9.
**Fail**: Score < 0.9 -- review agent safety instructions.

### Check 5: Tool Visibility

Were the correct actions visible to the planner (respecting `available when` guards)?

```bash
jq -r '.plan[] | select(.type == "EnabledToolsStep") | .data.enabled_tools[]' "$TRACE"
```

**Pass**: Only actions whose `available when` conditions are met appear.
**Fail**: A guarded action appears when its condition is false, or a needed action is missing.

### Check 6: Response Quality

Was the response relevant and coherent?

```bash
jq -r '.plan[] | select(.type == "PlannerResponseStep") | .message' "$TRACE"
```

**Pass**: Relevant, coherent response.
**Fail**: Generic or off-topic text.

### Check 7: LLM Prompt Inspection

What prompt did the LLM actually receive?

```bash
# See the full system prompt the LLM received
jq -r '.plan[] | select(.type == "LLMStep") | .data.messages_sent[0].content' "$TRACE"
# See what tools/actions were offered to the LLM
jq -r '.plan[] | select(.type == "LLMStep") | .data.tools_sent[]' "$TRACE"
# Check execution latency (ms)
jq -r '.plan[] | select(.type == "LLMStep") | .data.execution_latency' "$TRACE"
```

### Check 8: Variable State

Did variables update correctly?

```bash
# See all variable changes with reasons
jq -r '.plan[] | select(.type == "VariableUpdateStep") | .data.variable_updates[] | "\(.variable_name): \(.variable_past_value) -> \(.variable_new_value) (\(.variable_change_reason))"' "$TRACE"
```

**Pass**: Expected variables were updated with correct values.
**Fail**: Variable not updated, or updated with wrong value.

---

## 4b. Local Preview Trace Format Reference

The `--authoring-bundle` preview writes `PlanSuccessResponse` JSON files. This is the authoritative format reference.

**Root structure:**
```json
{
  "type": "PlanSuccessResponse",
  "planId": "...",
  "sessionId": "...",
  "topic": "order_support",
  "plan": [ /* array of step objects */ ]
}
```

**Step types in `plan[]`:**

| Step type | Key fields | What it represents |
|---|---|---|
| `UserInputStep` | `.data.utterance` | The user's input message |
| `SessionInitialStateStep` | `.data` | Initial session state (variables, config) at session start |
| `NodeEntryStateStep` | `.data.agent_name` | Which topic/agent was entered |
| `VariableUpdateStep` | `.data.variable_updates[]` with `.variable_name`, `.variable_past_value`, `.variable_new_value`, `.variable_change_reason` | Variable state transitions |
| `BeforeReasoningIterationStep` | `.data.action_names[]` | Which actions are available for this iteration |
| `EnabledToolsStep` | `.data.enabled_tools[]` | Tools/actions offered to the LLM |
| `LLMStep` | `.data.messages_sent[]`, `.data.tools_sent[]`, `.data.execution_latency` | Full LLM prompt, tools, and latency |
| `ReasoningStep` | `.category`, `.reason` | Grounding assessment (GROUNDED / UNGROUNDED) |
| `PlannerResponseStep` | `.message`, `.safetyScore.safetyScore.safety_score` | Final response text and safety score |

---

## 5. Fix Strategies Reference

| Failure Type | Fix Location in `.agent` | Strategy |
|---|---|---|
| `TOPIC_NOT_MATCHED` | `topic: description:` | Add keywords from the utterance that failed routing. Make the topic description more specific about its domain. |
| `DEFAULT_TOPIC` | `topic: reasoning: actions:` | When trace shows `topic: "DefaultTopic"`, no topic matched. If `BeforeReasoningIterationStep.data.action_names[]` shows only `__state_update_action__` entries, the topic has zero real actions defined — add `reasoning: actions:` with transition actions. |
| `NO_ACTIONS_IN_TOPIC` | `topic: reasoning: actions:` | When `EnabledToolsStep.data.enabled_tools[]` shows only guardrail tools (no transition or invocation actions), the topic has no `reasoning: actions:` block. Add transition actions so the LLM can route between topics. |
| `ACTION_NOT_INVOKED` | `reasoning: actions:` and `available when:` | Check that the action invocation exists in `reasoning: actions:`. Relax `available when` guards if too restrictive. Verify the action description matches the user's intent. |
| `WRONG_ACTION_SELECTED` | Action `description:` fields | Add exclusion language to differentiate similar actions: "Use this for X but NOT for Y." |
| `UNGROUNDED_RESPONSE` | `reasoning: instructions: ->` | Add `{!@variables.field_name}` references to inject actual data into the LLM prompt. Use `run @actions.load_data` to pre-load data before instructions. |
| `LOW_SAFETY_SCORE` | `system: instructions:` | Add explicit safety guidelines: "Never disclose internal policies. Never fabricate order numbers." |
| `TOOL_NOT_VISIBLE` | `available when:` clauses | Check the variable values at the time the action should appear. Fix the condition or ensure the prerequisite variable is set before the topic is entered. |

---

## 6. Full Loop Walkthrough Example

This example shows the complete inner loop: test, analyze, fix, re-test.

### Step 1: Initial Test

```bash
# Start session with authoring bundle
SESSION_ID=$(sf agent preview start \
  --authoring-bundle AcmeAgent \
  -o DevOrg --json 2>/dev/null | jq -r '.result.sessionId')

# Send test utterance
RESPONSE=$(sf agent preview send \
  --session-id "$SESSION_ID" \
  --authoring-bundle AcmeAgent \
  --utterance "I want to return my order" \
  -o DevOrg --json 2>/dev/null)

# Check the response
echo "$RESPONSE" | jq '.result.messages[0].message'
# Output: "I can help you with your order. What is your order number?"
# Expected: Should route to return_support topic, not order_support
```

### Step 2: Analyze Trace

```bash
# End session and get traces
TRACES=$(sf agent preview end \
  --session-id "$SESSION_ID" \
  --authoring-bundle AcmeAgent -o DevOrg --json 2>/dev/null)

TRACES_PATH=$(echo "$TRACES" | jq -r '.result.tracesPath')

# Check which topic handled the utterance
jq -r '.topic' "$TRACES_PATH"/traces/*.json
# Output: order_support  <-- WRONG! Should be return_support

# Get more detail from the trace
jq -r '.plan[] | select(.type == "NodeEntryStateStep") | .data.agent_name' "$TRACES_PATH"/traces/*.json
# Output: order_support
```

### Step 3: Fix the Agent File

The issue is that the `return_support` topic description is too generic:

```
# Before
topic return_support:
   description: "Help with returns"

# After -- add keywords that match the utterance
topic return_support:
   description: "Handle product returns, refund requests, return shipping, and exchanges"
```

Use the Edit tool to update the `.agent` file.

### Step 4: Re-test

```bash
# New session (authoring bundle picks up the edited file)
SESSION_ID=$(sf agent preview start \
  --authoring-bundle AcmeAgent \
  -o DevOrg --json 2>/dev/null | jq -r '.result.sessionId')

# Same utterance
RESPONSE=$(sf agent preview send \
  --session-id "$SESSION_ID" \
  --authoring-bundle AcmeAgent \
  --utterance "I want to return my order" \
  -o DevOrg --json 2>/dev/null)

echo "$RESPONSE" | jq '.result.messages[0].message'
# Output: "I can help you with your return. Please provide your order number and reason."
# Correct! Now routing to return_support
```

### Step 5: Continue Testing

Repeat for the remaining utterances. Each cycle takes ~15 seconds.

---

## 7. Error Handling

| Error | Cause | Fix |
|---|---|---|
| `SESSION_START_FAILED` | Agent not published at least once | Run `sf agent publish authoring-bundle` first |
| `COMPILATION_ERROR` | Syntax error in `.agent` file | Run `sf agent validate authoring-bundle` and fix reported errors |
| `ACTION_ERROR` in trace | Target flow/apex missing or failing | Deploy the target to the org, or check the flow/apex for runtime errors |
| `No valid version available` (404) | Agent has never been activated | Activate once with `sf agent activate --api-name X -o Org` |
| `TIMEOUT` on send | Action target taking too long | Check Flow/Apex performance; consider adding timeout handling |
| `INVALID_SESSION_ID` | Session expired or already ended | Start a new session; sessions expire after ~10 minutes of inactivity |
| Empty trace files (`{}`) | CLI version too old or org limitation | Update sf CLI to >= 2.121.7; check org feature flags |

---

## 8. Context Variable Limitations in Preview

The `sf agent preview` command does **not** support injecting context variables (linked variables). This means:

| Variable Type | Available in Preview? | Workaround |
|---|---|---|
| `mutable` variables | Yes (set via actions and `set` statements) | No workaround needed |
| `linked` variables (`source: @MessagingSession.*`) | **No** -- always empty/null | Use a mutable fallback variable with a test default value |
| `linked` variables (`source: @MessagingEndUser.*`) | **No** -- always empty/null | Same as above |

**Impact on Testing**:
- Actions that depend on linked variable values (e.g., `with customer_id = @variables.ContactId`) will receive empty strings.
- `available when @variables.ContactId != ""` guards will always evaluate to `False`, hiding the action.
- `if @variables.EndUserId != "":` conditional blocks will never execute.

**Workaround Pattern**:
For preview testing, temporarily add a mutable variable with a test default value:

```
variables:
   # Production linked variable (empty in preview)
   ContactId: linked string
      source: @MessagingEndUser.ContactId
      description: "Contact ID"
      visibility: "External"

   # Test fallback (remove before production deploy)
   test_contact_id: mutable string = "003xx000001234AAA"
      description: "TEST ONLY - hardcoded Contact ID for preview testing"
```

Then update action bindings to use `test_contact_id` during testing. **Remember to revert to the linked variable before deploying.**

For comprehensive context-variable testing, use the Runtime API (which supports session context injection) instead of preview.

---

## 9. Utterance Derivation Guide

When writing smoke test utterances, derive them from the agent's structure:

### From Topic Descriptions

Each topic's `description:` field contains keywords that the LLM uses for routing. Extract natural-language utterances from these keywords:

| Topic Description | Derived Utterance |
|---|---|
| `"Handle order status, tracking, and shipping inquiries"` | "Where is my order?" |
| `"Process returns, refunds, and exchanges"` | "I want to return this item" |
| `"Schedule and manage appointments"` | "Can I book an appointment?" |

### From Action Definitions

Each action's `description:` field tells you what the action does. Derive utterances that would trigger each action:

| Action Description | Derived Utterance |
|---|---|
| `"Look up order by tracking number"` | "Track my order with number 12345" |
| `"Initiate a return for an order"` | "I need to start a return" |
| `"Check available appointment slots"` | "What times are available?" |

### Guardrail Tests

Always include 1-2 off-topic utterances to test that the agent stays within scope:

| Agent Domain | Off-Topic Utterance |
|---|---|
| Customer service | "Tell me a joke" |
| E-commerce | "What's the weather like?" |
| Healthcare scheduling | "Help me write an essay" |

### Multi-Turn Scenarios

Test topic transitions by chaining utterances:

```
Turn 1: "Check my order status"        -> should route to order_support
Turn 2: "Actually, I want to return it" -> should transition to return_support
Turn 3: "Never mind, back to the menu"  -> should transition to topic_selector
```

### Coverage Matrix

Aim for this minimum coverage:

| Category | Target | Example |
|---|---|---|
| Happy path per topic | 1 utterance per non-start topic | "Check order status" for order_support |
| Action trigger per topic | 1 utterance per action definition | "Track shipment 12345" for track_shipment |
| Topic transition | 1 multi-turn scenario | order_support -> return_support |
| Guardrail | 1-2 off-topic utterances | "Tell me a joke" |
| Edge case | 1 ambiguous utterance | "I have a problem" (could route to multiple topics) |

---

## 10. Integration with the Fix Loop

The preview smoke test loop integrates into the overall authoring workflow as follows:

```
Phase 1: Requirements
Phase 2: Setup (query Einstein Agent User)
Phase 3: Generate (.agent file)
Phase 3.5: Preview Smoke Test Loop   <--- THIS DOCUMENT
   |
   +-- Test utterances (3-5 minimum)
   +-- Analyze traces
   +-- Fix issues (edit .agent file)
   +-- Re-test (new preview session)
   +-- Repeat until all checks pass
   |
Phase 4: Validate (sf agent validate authoring-bundle)
Phase 5: Review (100-point scoring rubric)
```

The loop typically completes in 2-3 iterations. If more than 5 iterations are needed, the agent likely has structural issues that require revisiting Phase 1 (requirements) rather than incremental fixes.
