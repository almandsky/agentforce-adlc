<!-- Parent: adlc-author/SKILL.md -->
# Debugging Guide

> How to read traces, diagnose issues, and fix Agent Script problems using the four debugging views.

---

## 1. Four Debugging Views

Agentforce provides four complementary views for debugging agent behavior:

### View 1: Interaction Details

**Where**: Agentforce Studio > Sessions > Select a session > Interaction Details panel

Shows the high-level conversation flow: each turn with the user message, agent response, and which topic handled it. Use this to quickly identify topic routing issues.

**Key information**:
- User utterance per turn
- Agent response per turn
- Active topic per turn
- Session duration and turn count

### View 2: Trace Waterfall

**Where**: Agentforce Studio > Sessions > Select a turn > Trace Waterfall

Shows the step-by-step execution within a single turn. Each step is a colored span representing a different execution phase. Use this for diagnosing why a specific turn behaved incorrectly.

**Key information**:
- Execution order of steps
- Duration of each step (identify bottlenecks)
- Step types (topic, LLM, action, guardrails)
- Input/output data per step

### View 3: Variable State

**Where**: Trace Waterfall > Select an ACTION_STEP > Pre/Post Variables

Shows the variable snapshot before and after each action step. Use this to track how state changes during execution.

**Key information**:
- `preVars`: Variable values before the action ran
- `postVars`: Variable values after the action completed
- Diff between pre and post reveals what changed

### View 4: Script View

**Where**: The `.agent` file itself (read with a text editor or the Read tool)

The source of truth for agent behavior. Cross-reference trace data against the script to identify gaps between intent and implementation.

---

## Two Trace Formats

There are two different trace formats depending on the data source:

**STDM trace spans** (Data Cloud, used by `adlc-optimize` Phase 1):
Step types: `TOPIC_STEP`, `LLM_STEP`, `ACTION_STEP`, `TRUST_GUARDRAILS_STEP`, `SESSION_END`, `SYSTEM_STEP`
These are high-level spans from the runtime telemetry pipeline.

**Local preview trace steps** (`--authoring-bundle`, used by `adlc-author`/`adlc-test`):
Step types: `UserInputStep`, `NodeEntryStateStep`, `VariableUpdateStep`, `BeforeReasoningIterationStep`, `EnabledToolsStep`, `LLMStep`, `ReasoningStep`, `PlannerResponseStep`
These are fine-grained steps with full LLM prompt, variable state, and grounding details.

The STDM span types in Section 2 below correspond to the Data Cloud telemetry format. For local preview trace analysis, see Section 7.

## 2. Six STDM Span Types

Each STDM trace step has a `type` field. The six types you'll encounter:

| Span Type | Color (UI) | What It Represents | Duration Includes |
|---|---|---|---|
| `TOPIC_STEP` | Blue | Topic selection/routing | Time to evaluate topic descriptions and select a topic |
| `LLM_STEP` | Purple | LLM reasoning | Prompt assembly + model inference + response parsing |
| `ACTION_STEP` | Green | Action execution | Input binding + target execution (Flow/Apex/API) + output capture |
| `SESSION_END` | Gray | Session termination | N/A (marker only) |
| `TRUST_GUARDRAILS_STEP` | Orange | Safety/compliance check | Instruction adherence evaluation |
| `SYSTEM_STEP` | Light gray | Internal framework operations | Variable initialization, transition logic |

### Span Hierarchy

Within a single turn, spans execute in this order:

```
TOPIC_STEP           (which topic handles this turn?)
  |
  v
LLM_STEP             (assemble prompt, call LLM, get response)
  |
  v
ACTION_STEP          (execute the action the LLM selected)
  |
  v
TRUST_GUARDRAILS_STEP (check if response follows instructions)
  |
  v
[Loop: back to LLM_STEP if more actions needed]
```

---

## 3. Reading a Trace Waterfall

### Healthy Trace Pattern

A normal single-action turn looks like:

```
[TOPIC_STEP]  order_support              12ms
[LLM_STEP]   plan_generation           1,245ms
[ACTION_STEP] get_order_status           832ms
[LLM_STEP]   response_generation         456ms
[TRUST_GUARDRAILS_STEP] InstructionAdherence  34ms
```

Total: ~2,579ms. This is a healthy trace -- topic selected quickly, LLM reasoned, action executed, response generated.

### Red Flags in Traces

| Pattern | Indicates | Investigation |
|---|---|---|
| `TOPIC_STEP` to wrong topic | Topic description mismatch | Compare utterance to topic descriptions |
| `LLM_STEP` > 5,000ms | Slow model inference or large prompt | Check token count; simplify instructions |
| `ACTION_STEP` > 10,000ms | Slow action target | Check Flow/Apex performance |
| `ACTION_STEP` with non-null `error` | Action runtime failure | Read error message; check Flow fault paths |
| No `ACTION_STEP` after `LLM_STEP` | LLM didn't select any action | Check action descriptions and availability |
| Multiple `TOPIC_STEP` in one turn | Topic bouncing | Topics are too similar or have overlapping descriptions |
| `TRUST_GUARDRAILS_STEP` with `value: LOW` | Response diverged from instructions | Read instructions; check if they're specific enough |
| Same `LLM_STEP` + `ACTION_STEP` repeating 3+ times | Loop detection | Check for missing transition after action completion |

---

## 4. Variable State Analysis

Variable state tracking is the most powerful debugging technique. It tells you exactly what the agent "knew" at each point in execution.

### Reading Pre/Post Variable Snapshots

Each `ACTION_STEP` in the trace includes:
- `preVars` (or `pre_vars` in STDM): Variable values BEFORE the action ran
- `postVars` (or `post_vars` in STDM): Variable values AFTER the action completed

### Common Variable State Issues

**Issue 1: Variable Never Set**

```
preVars:  { "order_id": "", "order_status": "" }
postVars: { "order_id": "", "order_status": "" }
```

The action ran but no output was captured. Check:
- Is there a `set @variables.order_status = @outputs.status` binding?
- Does the action output field name match (`status` vs `Status` vs `order_status`)?
- Did the action actually return data (check the action's `output` field)?

**Issue 2: Variable Overwritten**

```
Turn 1 postVars: { "order_id": "ORD-123", "customer_name": "Alice" }
Turn 2 preVars:  { "order_id": "", "customer_name": "Alice" }
```

`order_id` was reset between turns. Check:
- Is another action's `set` clause overwriting it with an empty value?
- Is a `before_reasoning:` block resetting it?
- Did a topic transition occur that reinitializes variables?

**Issue 3: Wrong Variable Value**

```
preVars:  { "risk_score": "85" }
postVars: { "risk_score": "0" }
```

The action returned `0` instead of keeping `85`. Check:
- Is the `run @actions.load_data` executing again (latch pattern missing)?
- Is the Flow returning a default value when the record isn't found?

### Variable Diff Recipe

**For STDM traces** (from Data Cloud / `adlc-optimize`):
```bash
# STDM uses pre_vars/post_vars on ACTION_STEP spans
jq -r '
  .steps[]
  | select(.step_type == "ACTION_STEP")
  | "Action: \(.name)\n  Pre:  \(.pre_vars)\n  Post: \(.post_vars)\n"
' "$TRACE_FILE"
```

**For local preview traces** (from `--authoring-bundle`):
```bash
# Local traces use VariableUpdateStep with detailed change reasons
jq -r '
  .plan[]
  | select(.type == "VariableUpdateStep")
  | .data.variable_updates[]
  | "\(.variable_name): \(.variable_past_value) -> \(.variable_new_value) (\(.variable_change_reason))"
' "$TRACE_FILE"
```

**Internal variable: `AgentScriptInternal_agent_instructions`**
Local preview traces show how the LLM prompt is assembled incrementally via `VariableUpdateStep` entries for `AgentScriptInternal_agent_instructions`. Each update appends one line from the `start_agent` or topic `reasoning: instructions:` block. This reveals exactly what instruction text the LLM receives — useful for debugging instruction assembly issues.

---

## 5. Five Common Debug Patterns

### Pattern 1: Topic Misroute

**Symptom**: User asks about returns, but the `order_support` topic handles it instead of `return_support`.

**Diagnosis**:
1. Check the `TOPIC_STEP` in the trace -- which topic was selected?
2. Compare the topic descriptions:
   - `order_support.description: "Handle orders, tracking, returns"`  <-- "returns" here is the problem
   - `return_support.description: "Process refund requests"`

**Fix**:
- Remove "returns" from `order_support` description
- Add "returns" to `return_support` description
- Make descriptions mutually exclusive

### Pattern 2: Action Not Invoked

**Symptom**: User asks to cancel an order, but the LLM gives a generic response without calling the `cancel_order` action.

**Diagnosis**:
1. Check if `cancel_order` appears in the trace's available actions
2. If not, check `available when` guards:
   - `available when @variables.order_id != ""` -- is `order_id` set?
   - `available when @variables.is_verified == True` -- is verification done?
3. If available but not selected, check the action description -- is it specific enough?

**Fix**:
- Relax guards if too restrictive
- Make action description match the user's likely phrasing
- Add the action name to topic instructions: "Use `@actions.cancel_order` when the customer wants to cancel."

### Pattern 3: Infinite Loop

**Symptom**: Agent keeps asking the same question or executing the same action repeatedly (3+ times).

**Diagnosis**:
1. Check the trace for repeating `ACTION_STEP` patterns
2. Look at variable state -- is a variable expected to change but staying the same?
3. Check for missing `transition to` after success condition

**Fix**:
- Add post-action check at TOP of instructions with `transition to`
- Use a latch variable (`data_loaded: mutable boolean = False`) to prevent re-execution
- Add `after_reasoning:` block with transition logic

### Pattern 4: Empty Action Outputs

**Symptom**: Action executes successfully (no error) but all output variables remain empty.

**Diagnosis**:
1. Check the `ACTION_STEP` output field in the trace -- what did the action return?
2. Compare output field names in the trace vs. the `set` clause:
   - Trace output: `{"Status": "Active", "Name": "Acme"}`
   - Set clause: `set @variables.status = @outputs.status`  <-- case mismatch! Should be `@outputs.Status`
3. Check the Flow/Apex -- is it returning values in the expected output variables?

**Fix**:
- Match case exactly between Agent Script output names and Flow/Apex output variable names
- Verify the Flow/Apex actually populates the output variables (add debug logs)

### Pattern 5: Stale Instructions

**Symptom**: Agent behaves as if it has old instructions despite `.agent` file updates.

**Diagnosis**:
1. Check if the agent was re-published after the `.agent` file edit
2. Query the live instructions:
   ```bash
   sf data query \
     --query "SELECT Id, Description FROM GenAiPluginInstructionDef WHERE GenAiPluginDefinitionId = '<topic_id>'" \
     -o TargetOrg --json
   ```
3. Compare live instruction text to `.agent` file text

**Fix**:
- Re-publish: `sf agent publish authoring-bundle --api-name X -o Org --json`
- If publish fails, use Tooling API PATCH as described in the optimization workflow
- Verify with another query after publish

---

## 6. Diagnostic Checklist

Run through this checklist for any agent issue:

### Quick Checks (< 1 minute)

- [ ] Is the `.agent` file syntactically valid? (`sf agent validate authoring-bundle --api-name X -o Org --json`)
- [ ] Is the agent published? (`sf data query --query "SELECT Id, DeveloperName FROM GenAiPlannerDefinition WHERE DeveloperName LIKE '%AgentName%'" -o Org --json`)
- [ ] Is the agent activated? (Check in Setup > Agentforce > Agents)
- [ ] Do all action targets exist in the org? (Query each Flow/Apex class)
- [ ] Is the Einstein Agent User valid? (`sf data query -q "SELECT Username FROM User WHERE Profile.Name = 'Einstein Agent User' AND IsActive = true" -o Org --json`)

### Trace Analysis (5-10 minutes)

- [ ] Run a preview session with the failing utterance
- [ ] Check `TOPIC_STEP` -- correct topic selected?
- [ ] Check `LLM_STEP` -- was the right instruction text assembled?
- [ ] Check `ACTION_STEP` -- was an action called? Which one?
- [ ] Check `ACTION_STEP` outputs -- did the action return expected data?
- [ ] Check variable state (pre/post) -- are variables updating correctly?
- [ ] Check `TRUST_GUARDRAILS_STEP` -- is instruction adherence HIGH?

### Deep Investigation (15-30 minutes)

- [ ] Query `GenAiPluginInstructionDef` for verbatim live instructions
- [ ] Compare live instructions to `.agent` file (stale publish?)
- [ ] Check topic descriptions for overlap (`GenAiPluginDefinition.Description`)
- [ ] Review action I/O name matching (Agent Script vs Flow/Apex)
- [ ] Test multiple utterances for the same intent (consistency check)
- [ ] Run 3 preview sessions to distinguish deterministic vs intermittent failures

---

## 7. Programmatic Trace Access

### Local Trace Files (from `sf agent preview --authoring-bundle`)

```bash
# List all trace sessions for an agent
ls -la .sfdx/agents/MyAgent/sessions/

# Read all traces for the most recent session
for TRACE in .sfdx/agents/MyAgent/sessions/*/traces/*.json; do
  echo "=== $(basename "$TRACE") ==="
  jq '.' "$TRACE"
done
```

### jq Recipes (Local Preview Traces)

**Check topic routing:**
```bash
jq -r '.topic' "$TRACE"
jq -r '.plan[] | select(.type == "NodeEntryStateStep") | .data.agent_name' "$TRACE"
```

**Check action availability:**
```bash
jq -r '.plan[] | select(.type == "BeforeReasoningIterationStep") | .data.action_names[]' "$TRACE"
jq -r '.plan[] | select(.type == "EnabledToolsStep") | .data.enabled_tools[]' "$TRACE"
```

**Extract LLM prompt (what the model actually saw):**
```bash
jq -r '.plan[] | select(.type == "LLMStep") | .data.messages_sent[] | "\(.role): \(.content[:200])..."' "$TRACE"
```

**Extract tools offered to LLM:**
```bash
jq -r '.plan[] | select(.type == "LLMStep") | .data.tools_sent[]' "$TRACE"
```

**Check execution latency:**
```bash
jq -r '.plan[] | select(.type == "LLMStep") | .data.execution_latency' "$TRACE"
```

**Check grounding assessment:**
```bash
jq -r '.plan[] | select(.type == "ReasoningStep") | {category: .category, reason: .reason}' "$TRACE"
```

**Check safety score:**
```bash
jq -r '.plan[] | select(.type == "PlannerResponseStep") | .safetyScore.safetyScore.safety_score' "$TRACE"
```

**Get response text:**
```bash
jq -r '.plan[] | select(.type == "PlannerResponseStep") | .message' "$TRACE"
```

**Variable state timeline:**
```bash
jq -r '
  .plan[]
  | select(.type == "VariableUpdateStep")
  | .data.variable_updates[]
  | "\(.variable_name): \(.variable_past_value) -> \(.variable_new_value) (\(.variable_change_reason))"
' "$TRACE"
```

**Count UNGROUNDED retries:**
```bash
jq '[.plan[] | select(.type == "ReasoningStep")] | length' "$TRACE"
# 1 = normal, 2+ = UNGROUNDED retry happened
```

**All step types in order:**
```bash
jq -r '.plan[] | .type' "$TRACE"
```

---

## 8. Trace to Agent Script Mapping

This table maps trace step data back to the corresponding Agent Script constructs:

| Trace Field | Agent Script Source | How to Find |
|---|---|---|
| `TOPIC_STEP.name` | `topic <name>:` | The topic block's identifier |
| `TOPIC_STEP` selection | `topic <name>: description:` | Topic description used for LLM routing |
| `LLM_STEP.input` (instructions portion) | `reasoning: instructions:` | Resolved instruction text from Phase 1 |
| `LLM_STEP.input` (actions portion) | `reasoning: actions:` descriptions | Available action descriptions (after `available when` filtering) |
| `ACTION_STEP.name` | `reasoning: actions: <invocation_name>:` | The Level 2 invocation name |
| `ACTION_STEP.input` | `with param = value` bindings | Input bindings on the invocation |
| `ACTION_STEP.output` | `set @variables.X = @outputs.Y` | Output bindings (what's captured) |
| `ACTION_STEP.error` | Target Flow/Apex runtime error | Not in Agent Script -- check the target's error handling |
| `preVars` / `postVars` | `variables:` block | Variable definitions and their current values |
| `TRUST_GUARDRAILS_STEP.output` | `system: instructions:` + `reasoning: instructions:` | Combined instruction text evaluated for adherence |

### Mapping Example

Given this trace excerpt:
```json
{
  "type": "ACTION_STEP",
  "name": "lookup_order",
  "input": "{\"order_id\": \"ORD-456\"}",
  "output": "{\"status\": \"Shipped\", \"tracking_url\": \"https://track.example.com/456\"}",
  "preVars": "{\"order_id\": \"ORD-456\", \"order_status\": \"\"}",
  "postVars": "{\"order_id\": \"ORD-456\", \"order_status\": \"Shipped\"}",
  "error": null,
  "durationMs": 1234
}
```

The corresponding Agent Script:
```
# Level 2 invocation (the "name" matches "lookup_order")
reasoning:
   actions:
      lookup_order: @actions.get_order
         description: "Look up order"
         with order_id = @variables.order_id       # input: order_id = "ORD-456"
         set @variables.order_status = @outputs.status  # postVars shows "Shipped"
```

---

## 9. Planner Engine Differences

Agentforce uses different planner engines depending on the agent configuration. The planner engine affects how instructions are processed and how actions are selected.

### Engine Types

| Engine | Used By | Behavior |
|---|---|---|
| **ReAct** | Default for most agents | Reason-Act-Observe loop. LLM reasons step-by-step, selects one action at a time. |
| **Plan-then-Execute** | Agents with multi-step planning enabled | LLM generates a full plan upfront, then executes actions in sequence. |
| **Deterministic** | `instructions: ->` with `run` and `transition to` | No LLM involved. Agent Script runtime executes constructs directly. |

### How the Engine Affects Debugging

| Behavior | ReAct | Plan-then-Execute |
|---|---|---|
| Action selection | One action per LLM call | Multiple actions planned, executed sequentially |
| Trace pattern | Alternating LLM_STEP + ACTION_STEP | LLM_STEP (plan) + multiple ACTION_STEPs |
| Re-resolution | After each action | After entire plan completes |
| Error recovery | LLM re-reasons on next turn | Plan may abort on first error |

### Identifying the Engine in Traces

- **ReAct**: You'll see alternating `LLM_STEP` -> `ACTION_STEP` -> `LLM_STEP` -> `ACTION_STEP` patterns
- **Plan-then-Execute**: You'll see one `LLM_STEP` followed by multiple `ACTION_STEP`s before the next `LLM_STEP`
- **Deterministic**: You'll see `SYSTEM_STEP` or direct `ACTION_STEP` without preceding `LLM_STEP`

### Engine-Specific Debugging Tips

**ReAct**:
- If the LLM selects the wrong action, check the action descriptions -- they're evaluated independently each turn
- Post-action re-resolution means your `instructions: ->` conditions will be re-checked after each action

**Plan-then-Execute**:
- If a multi-step plan fails midway, check which action failed and whether its inputs depended on a previous action's outputs
- The plan is committed upfront, so variable changes during execution don't affect action selection

**Deterministic**:
- `run` and `transition to` in `instructions: ->` execute without LLM involvement
- If a deterministic path fires unexpectedly, check variable values -- the `if` condition may be evaluating differently than expected
- Use `preVars` on the trace to see exactly what values the condition saw

---

## 10. Debugging Workflow Summary

```
1. Reproduce
   - Run `sf agent preview` with the failing utterance
   - Collect trace files

2. Identify the step that went wrong
   - Check TOPIC_STEP: correct topic?
   - Check LLM_STEP: correct instructions assembled?
   - Check ACTION_STEP: correct action? Correct inputs? Error?
   - Check variable state: expected values?

3. Map trace back to Agent Script
   - Which topic block? Which instructions block?
   - Which action definition? Which invocation?
   - Which variable? Which binding?

4. Fix the Agent Script
   - Edit the .agent file
   - Validate: sf agent validate authoring-bundle
   - Re-test with sf agent preview

5. Verify
   - Run the same utterance again
   - Confirm the trace now shows expected behavior
   - Run 3 times to confirm consistency
```
