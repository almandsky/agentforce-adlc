---
name: adlc-optimize
description: Analyze Agentforce session traces from Data Cloud, reproduce issues with live preview, and improve the .agent file directly
allowed-tools: Bash Read Write Edit Glob Grep
argument-hint: "<org-alias> [--agent-file <path>] [--session-id <id>] [--days <n>]"
---

# Agentforce Optimize (ADLC)

Improve Agentforce agents using real conversation data from the Session Trace Data Model (STDM) in Data Cloud.

**Three-phase workflow:**
- **Observe** -- Deploy helper class, query STDM sessions, reconstruct conversations, identify issues
- **Reproduce** -- Use `sf agent preview` to simulate problematic conversations live
- **Improve** -- Edit the `.agent` file directly, validate, publish, verify

---

## Routing

Gather these inputs before starting:

- **Org alias** (required)
- **Agent API name** (required for preview and deploy; ask if not provided)
- **Agent file path** (optional) -- path to the `.agent` file, typically `force-app/main/default/aiAuthoringBundles/<AgentName>/<AgentName>.agent`. Auto-detect if not provided.
- **Session IDs** (optional) -- analyze specific sessions; if absent, query last 7 days
- **Days to look back** (optional, default 7)

Determine intent from user input:

- **No specific action** -> run all three phases: Observe -> surface issues -> ask if user wants to Reproduce and/or Improve
- **"analyze" / "sessions" / "what's wrong"** -> Phase 1 only, then suggest next steps
- **"reproduce" / "test" / "preview"** -> Phase 2 (run Phase 1 first if no issues in hand)
- **"fix" / "improve" / "update"** -> Phase 3 (run Phase 1 first if no issues in hand)

### Resolve agent name

Before any STDM query, resolve the user-provided agent name against the org to get the exact `MasterLabel` and `DeveloperName`:

```bash
sf data query \
  --query "SELECT Id, MasterLabel, DeveloperName FROM GenAiPlannerDefinition WHERE MasterLabel LIKE '%<user-provided-name>%' OR DeveloperName LIKE '%<user-provided-name>%'" \
  -o <org> --json
```

- `MasterLabel` = display name used by STDM `findSessions` and Agent Builder UI (e.g. "Lennar Agent")
- `DeveloperName` = API name with version suffix used in metadata (e.g. "LennarAgent_v9")
- The `--api-name` flag for `sf agent preview/activate/publish` uses `DeveloperName` **without** the `_vN` suffix (e.g. "LennarAgent")

Store these values:
- `AGENT_MASTER_LABEL` -- for `findSessions()` agent filter
- `AGENT_API_NAME` -- `DeveloperName` without `_vN` suffix, for `sf agent` CLI commands
- `PLANNER_ID` -- the Salesforce record ID for this agent (needed by `findSessions` Planner fallback strategy)

### Locate the .agent file

**Step 1 -- Search locally:**

```bash
find <project-root>/force-app/main/default/aiAuthoringBundles -name "*.agent" 2>/dev/null
```

If the user provided an agent file path, use that directly. Otherwise, search for files matching `AGENT_API_NAME`.

**Step 2 -- If not found locally, retrieve from the org:**

```bash
sf project retrieve start --metadata "AiAuthoringBundle:<AGENT_API_NAME>" -o <org> --json
```

> **Known bug:** `sf project retrieve start` creates a double-nested path: `force-app/main/default/main/default/aiAuthoringBundles/...`. Fix it immediately after retrieve:

```bash
if [ -d "force-app/main/default/main/default/aiAuthoringBundles" ]; then
  mkdir -p force-app/main/default/aiAuthoringBundles
  cp -r force-app/main/default/main/default/aiAuthoringBundles/* \
    force-app/main/default/aiAuthoringBundles/
  rm -rf force-app/main/default/main
fi
```

**Step 3 -- Validate the retrieved file:**

Read the `.agent` file and verify it has proper Agent Script structure:
- `system:` block with `instructions:`
- `config:` block with `developer_name:`
- `start_agent` or `topic` blocks with `reasoning: instructions:`
- Each topic should have distinct `instructions:` content (not identical across topics)

Store the resolved path as `AGENT_FILE` for Phase 3.

---

## Phase 0: Discover Data Space

Before running any STDM query, determine the correct Data Cloud Data Space API name.

```bash
sf api request rest "/services/data/v66.0/ssot/data-spaces" -o <org>
```

Note: `sf api request rest` is a beta command -- do not add `--json` (that flag is unsupported and causes an error).

The response shape is:
```json
{
  "dataSpaces": [
    {
      "id": "0vhKh000000g3DjIAI",
      "label": "default",
      "name": "default",
      "status": "Active",
      "description": "Your org's default data space."
    }
  ],
  "totalSize": 1
}
```

The `name` field is the API name to pass to `AgentforceOptimizeService`.

**Decision logic:**
- If the command fails (e.g. 404 or permission error), fall back to `'default'` and note it as an assumption.
- Filter to only `status: "Active"` entries.
- If exactly one active Data Space exists, use it automatically and confirm to the user: "Using Data Space: `<name>`".
- If multiple active Data Spaces exist, show the list (label + name) and ask the user which to use.

Store the selected `name` value as `DATA_SPACE` for all subsequent steps.

### Prerequisite check: STDM DMOs

After deploying the helper class (step 1.0), run a quick probe to verify the STDM Data Model Objects exist in Data Cloud:

```bash
sf apex run -o <org> -f /dev/stdin << 'APEX'
ConnectApi.CdpQueryInput qi = new ConnectApi.CdpQueryInput();
qi.sql = 'SELECT ssot__Id__c FROM "ssot__AiAgentSession__dlm" LIMIT 1';
try {
    ConnectApi.CdpQueryOutputV2 out = ConnectApi.CdpQuery.queryAnsiSqlV2(qi, '<DATA_SPACE>');
    System.debug('STDM_CHECK:OK rows=' + (out.data != null ? out.data.size() : 0));
} catch (Exception e) {
    System.debug('STDM_CHECK:FAIL ' + e.getMessage());
}
APEX
```

**If the debug log contains `STDM_CHECK:FAIL` or a `404 NOT_FOUND` error mentioning `ssot__AiAgentSession__dlm`:**

The Session Trace Data Model is **not activated** in this org. This is a prerequisite for the optimize workflow. Inform the user:

> STDM (Session Trace Data Model) is not available in this org. The `ssot__AiAgentSession__dlm` DMO was not found in Data Cloud.
>
> To enable it:
> 1. Go to **Setup -> Data Cloud -> Data Streams** and verify "Agentforce Activity" data stream is active
> 2. Or go to **Setup -> Einstein -> Agentforce -> Settings** and enable "Session Trace Data"
> 3. After enabling, wait ~15 minutes for DMOs to be provisioned
>
> Without STDM, Phase 1 (Observe) cannot query session traces. You can still use Phase 2 (Reproduce) with `sf agent preview` to manually test the agent, and Phase 3 (Improve) to edit the `.agent` file directly.

**If `STDM_CHECK:OK`**, proceed to Phase 1.

---

## Phase 1: Observe -- Query STDM

### 1.0 Deploy helper class (once per org)

`AgentforceOptimizeService` is a bundled Apex class that queries all five STDM DMOs and returns clean JSON. Deploy it once; subsequent runs reuse the deployed class.

**Step 1 -- copy the class into the project:**

```bash
# Ensure the classes directory exists
mkdir -p <project-root>/force-app/main/default/classes

# Copy from the installed skill location
cp skills/adlc-optimize/apex/AgentforceOptimizeService.cls \
   <project-root>/force-app/main/default/classes/
cp skills/adlc-optimize/apex/AgentforceOptimizeService.cls-meta.xml \
   <project-root>/force-app/main/default/classes/
```

If the skill is installed globally via the installer, use the installed path:
```bash
cp ~/.claude/skills/adlc-optimize/apex/AgentforceOptimizeService.cls \
   <project-root>/force-app/main/default/classes/
cp ~/.claude/skills/adlc-optimize/apex/AgentforceOptimizeService.cls-meta.xml \
   <project-root>/force-app/main/default/classes/
```

**Step 2 -- ensure `sfdx-project.json` exists** (if absent, create a minimal one):

```json
{
  "packageDirectories": [{ "path": "force-app", "default": true }],
  "sourceApiVersion": "66.0"
}
```

**Step 3 -- deploy to the org:**

```bash
sf project deploy start \
  --metadata ApexClass:AgentforceOptimizeService \
  -o <org>
```

Confirm the deploy succeeds before proceeding. If it fails with a compile error, check that the org has Data Cloud enabled (the `ConnectApi.CdpQuery` namespace requires Data Cloud).

**Skip this step if `AgentforceOptimizeService` is already deployed** -- check with:
```bash
sf data query \
  --query "SELECT Id, Name FROM ApexClass WHERE Name = 'AgentforceOptimizeService'" \
  -o <org> --json
```

### 1.1 Find sessions

If the user provided session IDs, skip to 1.2. Otherwise, write `/tmp/stdm_find.apex` and run it (substitute actual ISO 8601 UTC timestamps, DATA_SPACE, and AGENT_API_NAME):

```apex
String result = AgentforceOptimizeService.findSessions(
    'DATA_SPACE',
    'START_ISO',
    'END_ISO',
    20,
    'AGENT_MASTER_LABEL'
);
System.debug('STDM_RESULT:' + result);
```

```bash
sf apex run --file /tmp/stdm_find.apex -o <org> --json
```

Parse: search for `DEBUG|STDM_RESULT:` (not `STDM_RESULT:` -- the first occurrence of that string is in the source echo, not the debug output) and extract the JSON that follows on that line:

```bash
python3 -c "
import json, sys
logs = json.load(sys.stdin)['result']['logs']
idx = logs.find('DEBUG|STDM_RESULT:')
print(logs[idx + len('DEBUG|STDM_RESULT:'):].split('\n')[0].strip())
" < /tmp/apex_result.json
```

The result is a JSON array of `SessionSummary` objects:
```json
[
  {
    "session_id": "...", "start_time": "...", "end_time": "...",
    "channel": "...", "duration_ms": 12345,
    "end_type": "USER_ENDED"
  }
]
```

- `end_time` and `duration_ms` may be `null` when the session has no recorded end event -- this is a normal STDM data quality gap, not an error.
- `end_type` values: `USER_ENDED`, `AGENT_ENDED`, or `null` (in-progress or not recorded). A `null` `end_type` may indicate an abandoned session.

**How agent filtering works** -- `findSessions` tries two strategies in order:

1. **Direct** (preferred): `ssot__AiAgentApiName__c = agentApiName` on `ssot__AiAgentSessionParticipant__dlm` -- no SOQL needed, uses a dedicated DMO field. Resolves in a single Data Cloud query.
2. **Planner fallback**: If strategy 1 returns no rows, SOQL: `SELECT Id FROM GenAiPlannerDefinition WHERE MasterLabel = :agentApiName` -> `ssot__ParticipantId__c IN (...)`. Both 15-char and 18-char ID formats are included (the DMO stores them inconsistently). If both strategies return empty, the query falls back to all sessions in the date range.

**If the debug log shows `Agent not found: <name>`**, no `GenAiPlannerDefinition` matched -- verify the agent name with:
```bash
sf data query --query "SELECT Id, MasterLabel, DeveloperName FROM GenAiPlannerDefinition" -o <org> --json
```
Use the exact `MasterLabel` value (not `DeveloperName`). `MasterLabel` matches the agent's display name; `DeveloperName` has a version suffix (e.g. `TeslaSupportAgent_v1`).

**If the debug log shows a warning about no sessions for the agent**, both strategies returned empty -- the agent may have no sessions in this date range, or Data Cloud ingestion may be delayed. The query falls back to all sessions in the date range.

### 1.2 Get conversation details

For up to 5 sessions (most recent first), write `/tmp/stdm_details.apex` and run it (substitute session IDs and DATA_SPACE):

```apex
String result = AgentforceOptimizeService.getMultipleConversationDetails(
    'DATA_SPACE',
    new List<String>{ 'SESSION_ID_1', 'SESSION_ID_2' }
);
System.debug('STDM_RESULT:' + result);
```

```bash
sf apex run --file /tmp/stdm_details.apex -o <org> --json
```

Parse using the same `DEBUG|STDM_RESULT:` pattern (see 1.1). Each element is a `ConversationData` object:

```json
{
  "session_id": "...",
  "start_time": "...", "end_time": "...", "channel": "...",
  "duration_ms": 45000,
  "end_type": "USER_ENDED",
  "session_variables": "{...}",
  "turn_count": 3,
  "action_error_count": 1,
  "turns": [
    {
      "interaction_id": "...",
      "topic": "CheckOrderStatus",
      "start_time": "...", "end_time": "...", "duration_ms": 8000,
      "telemetry_trace_id": "...",
      "messages": [
        { "message_type": "Input",  "text": "Where is my order?", "sent_at": "..." },
        { "message_type": "Output", "text": "I found your order...", "sent_at": "..." }
      ],
      "steps": [
        { "step_type": "TOPIC_STEP",  "name": "CheckOrderStatus" },
        { "step_type": "LLM_STEP",    "name": "...", "duration_ms": 3200,
          "generation_id": "abc123", "gateway_request_id": "def456" },
        { "step_type": "ACTION_STEP", "name": "GetOrderDetails",
          "input": "{...}", "output": "{...}", "error": null,
          "pre_vars": "{...}", "post_vars": "{...}", "duration_ms": 1500 }
      ]
    }
  ]
}
```

Key fields:
- `end_type` -- how the session ended (`USER_ENDED`, `AGENT_ENDED`, or null)
- `session_variables` -- final variable snapshot for the session (null when absent)
- `telemetry_trace_id` -- distributed tracing ID for this turn (null when absent)
- `generation_id` / `gateway_request_id` on `LLM_STEP` -- pass these step IDs to `getLlmStepDetails()` to retrieve the actual LLM prompt and response (useful for diagnosing LOW instruction adherence)

Treat any `null` field as absent/unknown. The `"NOT_SET"` sentinel is stripped by the service class before returning.

### 1.2b Get LLM prompt/response (optional, for LOW adherence)

When a session shows `TRUST_GUARDRAILS_STEP` with `'value': 'LOW'`, use `getLlmStepDetails()` to retrieve the actual LLM prompt and response for the associated `LLM_STEP` records. Pass the `step_id` values from steps where `step_type == "LLM_STEP"` and `generation_id != null`.

```apex
String result = AgentforceOptimizeService.getLlmStepDetails(
    'DATA_SPACE',
    new List<String>{ 'STEP_ID_1', 'STEP_ID_2' }
);
System.debug('STDM_RESULT:' + result);
```

```bash
sf apex run --file /tmp/stdm_llm.apex -o <org> --json
```

Returns a JSON array of `LlmStepDetail` objects:
```json
[
  {
    "step_id": "...",
    "interaction_id": "...",
    "step_name": "...",
    "prompt": "System: You are a Tesla support agent...\nUser: I want to schedule a test drive",
    "llm_response": "I'd be happy to help you schedule a test drive...",
    "generation_id": "...",
    "gateway_request_id": "..."
  }
]
```

- `prompt` -- full prompt from `GenAIGatewayRequest__dlm.prompt__c` (null if Einstein Audit DMO not enabled)
- `llm_response` -- model response from `GenAIGeneration__dlm.responseText__c` (null if not available)

Use these to confirm whether the agent's instructions were included in the prompt and whether the response deviated from them.

### 1.3 Reconstruct conversations

For each session, render the turn-by-turn timeline from the `ConversationData` JSON:

```
Session <session_id>  [<channel>]  <duration_ms>ms total  <turn_count> turns
------------------------------------------------------------
Turn 1  [Topic: <topic>]  <duration_ms>ms
  User:  <messages[type=Input].text>
  Agent: <messages[type=Output].text>
  Steps:
    TOPIC_STEP:  <name>
    LLM_STEP:    <name>  (<duration_ms>ms)
    ACTION_STEP: <name>  in: <input>  out: <output>  [ERROR: <error>]
```

### 1.4 Identify issues

Check each session for these patterns and classify by root cause category:

| Signal | Issue type | Root cause category |
|---|---|---|
| `step.error` not null AND `step.step_type == ACTION_STEP` | **Action error** -- Flow/Apex failed | `Agent Configuration Gap` or `Platform / Runtime Issue` |
| `turn.topic` doesn't match user intent | **Topic misroute** | `Agent Configuration Gap` -- topic description too broad/narrow |
| No `ACTION_STEP` when action was expected | **Action not called** -- instruction gap or missing action definition | `Agent Configuration Gap` -- action not wired in `.agent` file |
| `step.input` has wrong/empty values | **Wrong action input** -- `with` binding incorrect | `Agent Configuration Gap` -- binding misconfigured in `.agent` |
| `step.pre_vars` != `step.post_vars` unexpectedly | **Variable not captured** -- `set` binding missing | `Agent Configuration Gap` -- `set` binding missing in `.agent` |
| Same `topic` repeated 3+ turns with no resolution | **No transition** -- missing transition action | `Agent Configuration Gap` -- no `@utils.transition` to next topic |
| `step.duration_ms` > 10 000 | **Slow action** -- Flow/Apex performance | `Platform / Runtime Issue` |
| Only `LLM_STEP`s, no `ACTION_STEP`s at all | **No actions defined** -- topic has no action definitions or invocations | `Agent Configuration Gap` -- actions not defined in `.agent` |
| Agent answers knowledge question but gives generic/wrong response | **Knowledge miss** | `Knowledge Gap -- Infrastructure` (no space/action) or `Knowledge Gap -- Content` (article missing/stale) |
| `TRUST_GUARDRAILS_STEP` present and `output` contains `'value': 'LOW'` | **Low instruction adherence** -- agent responses drifting from instructions. Check `explanation` field. Run 1.2b to get the raw LLM prompt. | `Agent Configuration Gap` -- topic instructions unclear or conflicting |
| `end_type` is `null` on a short session (< 30s, 1-2 turns) | **Abandoned session** -- user may have hit a dead-end | `Agent Configuration Gap` or `Knowledge Gap` |
| Specialized topic appears for exactly 1 turn then session returns to entry permanently | **Handoff topic with no post-collection routing** -- topic collects input but has no instruction for what to do after | `Agent Configuration Gap` -- topic instructions missing the "after this, transition to X" step |
| A topic has zero sessions over the analysis window despite the agent being designed to handle those intents | **Dead topic** -- topic exists in `.agent` file but is never entered | `Agent Configuration Gap` -- entry topic handles the intent directly instead of routing |
| Agent responds with generic behavior despite the `.agent` file having rich per-topic instructions | **Publish drift** -- bundle was deployed but never properly published/activated | `Platform / Runtime Issue` -- re-publish the `.agent` file (Phase 3.5) |

**Root cause categories:**
- `Knowledge Gap -- Infrastructure` -- no `DataKnowledgeSpace`, no sources indexed, or knowledge action not deployed
- `Knowledge Gap -- Content` -- knowledge infrastructure set up but specific article/document is missing, stale, or not indexed
- `Agent Configuration Gap` -- topic description, action wiring, instruction text, bindings (`with`/`set`), transitions, or missing topic
- `Platform / Runtime Issue` -- timeouts, latency spikes, deploy failures, or transient errors

### 1.5 Present findings

**Sessions analyzed:**

| Session ID | Start | Duration | Turns | Topics seen | Action errors |
|---|---|---|---|---|---|

**Issues grouped by root cause category:**

For each root cause category that has at least one issue, list the evidence:

```
## Agent Configuration Gap
- [P1] <description> -- turn <N>, topic: <topic>, evidence: `<field>: "<value>"`

## Knowledge Gap -- Infrastructure
- [P1] <description> -- evidence: no DataKnowledgeSpace / knowledge action not deployed

## Knowledge Gap -- Content
- [P2] <description> -- evidence: knowledge action called but response generic/incorrect

## Platform / Runtime Issue
- [P3] <description> -- action `<name>` took <ms>ms
```

Priority: P1 = action errors, topic misroutes, LOW adherence; P2 = missing actions, variable bugs, knowledge gaps; P3 = performance, abandoned sessions

**Uplift estimate** (if 3+ sessions analyzed):

| Category | Issues found | Affected sessions | Projected improvement if fixed |
|---|---|---|---|
| Agent Configuration Gap | N | N | +N sessions fully resolved |
| Knowledge Gap | N | N | +N sessions partially resolved |

After presenting findings, **automatically proceed to Phase 1.5b** -- do not wait for the user to ask. The `.agent` file analysis is needed to confirm root causes before any fix can be proposed. Ask about Phase 2/3 only after 1.5b is complete.

### 1.5b Agent Config Evidence

Confirm root causes by analyzing the **retrieved `.agent` file** -- not by querying BPO metadata objects directly. The `.agent` file is the single source of truth.

> **Important:** Do NOT query `GenAiPluginDefinition`, `GenAiPluginInstructionDef`, or `GenAiFunction` directly. These are internal metadata objects managed by the Agent Script compiler. Always retrieve the `.agent` file from the org and analyze it. The only acceptable SOQL query is `GenAiPlannerDefinition` (for agent name resolution in the Routing step).

**Step 1 -- Retrieve the latest `.agent` file from the org:**

If the `.agent` file was not already retrieved in the Routing step, retrieve it now:

```bash
sf project retrieve start --metadata "AiAuthoringBundle:<AGENT_API_NAME>" -o <org> --json
```

Fix double-nesting if present:
```bash
if [ -d "force-app/main/default/main/default/aiAuthoringBundles" ]; then
  mkdir -p force-app/main/default/aiAuthoringBundles
  cp -r force-app/main/default/main/default/aiAuthoringBundles/* \
    force-app/main/default/aiAuthoringBundles/
  rm -rf force-app/main/default/main
fi
```

**Step 2 -- Analyze the `.agent` file structure:**

Read the `.agent` file and extract:

1. **Agent-level system prompt** -- `system: instructions:` content
2. **Per-topic descriptions** -- each `topic <name>: description:` value (controls routing)
3. **Per-topic instructions** -- each `topic <name>: reasoning: instructions:` content (controls LLM behavior)
4. **Action definitions** -- each `reasoning: actions:` block (what actions are available per topic)
5. **Action bindings** -- `with` (input) and `set` (output) bindings on each action
6. **Transitions** -- `@utils.transition to @topic.<name>` actions (how topics connect)

**Step 3 -- Cross-reference STDM symptoms against `.agent` file:**

| STDM symptom | What to check in `.agent` file | What to look for |
|---|---|---|
| Topic misroute | `topic <name>: description:` on affected topics | Description too broad -- overlaps with adjacent topic description |
| Action not called | `reasoning: actions:` in the topic + `reasoning: instructions:` | Action not defined in topic's `actions:` block, or not mentioned in `instructions:` |
| LOW instruction adherence | `reasoning: instructions:` in the topic | Instructions are vague, short, or conflict with other topics |
| Topic stuck, no transition | `reasoning: actions:` | No `@utils.transition to @topic.<next>` action defined |
| Wrong action input | `with <param> = @variables.<name>` | Wrong variable mapped, or variable not populated by prior step |
| Variable not captured | `set @variables.<name> = @outputs.<field>` | Missing `set` binding on the action |
| Knowledge miss | Look for `@actions.answer_*` or `retriever://` actions | Knowledge action not defined in any topic |

**Critical check -- identical instructions across topics:**

Compare the `reasoning: instructions:` content across all topics. If 2+ topics share the same instructions word-for-word, flag this as a critical issue:

```
CRITICAL: N topics share identical reasoning instructions.
    Each topic needs distinct, actionable instructions that tell the LLM
    what to do specifically for that topic's responsibility.
    Root cause: Agent Configuration Gap (identical instructions across all topics)
```

**Step 4 -- Publish drift detection:**

Compare what the `.agent` file contains against what the agent actually does (from STDM):

1. If the `.agent` file has rich per-topic instructions but STDM shows the agent giving generic responses, the bundle was likely deployed but never properly published/activated
2. If the `.agent` file defines actions that are never invoked in STDM sessions, the actions may not have been compiled into live metadata

If publish drift is detected:

```
PUBLISH DRIFT DETECTED: .agent file has topic-specific instructions and actions,
    but the agent behaves as if using generic/default configuration.
    Root cause: Platform / Runtime Issue -- bundle was never properly published,
    or publish failed silently after deploy.
    Fix: Re-publish the existing .agent file (no edits needed -- see Phase 3.5).
```

**Step 5 -- Knowledge infrastructure (only if knowledge gaps detected):**

```bash
# Does a knowledge space exist?
sf data query --query "SELECT Id, Name FROM DataKnowledgeSpace" -o <org> --json
```

Also check the `.agent` file for any action with `retriever://` target -- if none exists, knowledge infrastructure is not wired to the agent.

**Present findings alongside STDM evidence:**

```
Agent: <AgentName> (from .agent file)
  System prompt: "<first 200 chars of system: instructions:>"

Topics in .agent file:
  <topic_name>:
    Description: "<topic description>"
    Instructions: "<first 200 chars of reasoning instructions>"
    Actions: <list of action names>
    Transitions: <list of @utils.transition targets>

STDM symptom → .agent file evidence:
  <symptom> → <what the .agent file shows for this topic>
```

**Confirmed root cause format:**

```
Root cause: Agent Configuration Gap -- <topic_name>
  Current instruction (from .agent file):
  > <verbatim reasoning: instructions: content>

  Proposed fix (will be applied to .agent file):
  > <replacement instruction text>
```

---

## Phase 2: Reproduce -- Live Preview

Use `sf agent preview` to simulate conversations in an isolated session (no production data affected).

### 2.1 Build test scenarios from Phase 1 findings

Before opening a preview session, define one test scenario per confirmed issue:

| Issue type (Phase 1) | Test message to send | Expected behavior | Failure indicator |
|---|---|---|---|
| Dead topic -- never entered | Utterance that *should* route to that topic | `topic` in response = `<dead_topic>` | Topic stays `entry` |
| Action not called | Ask directly for the action's task | Action fires in the response | Conversational reply with no action invoked |
| Handoff topic -- no post-collection routing | Enter the handoff topic, then send a follow-up | Session continues in specialized topic | Falls back to `entry` after 1 turn |
| LOW adherence | Exact utterance from the flagged `TRUST_GUARDRAILS_STEP` | Response follows topic instruction | Generic/off-instruction answer |
| Knowledge miss | Question requiring a specific knowledge article | Agent cites correct information | Hallucinated or generic answer |
| Topic misroute | Utterance that belongs to topic A | `topic` = A in response | `topic` = B or `entry` |

### 2.2 Run a preview session

```bash
# Start a preview session
sf agent preview start --api-name <AgentApiName> -o <org> --json | tee /tmp/preview_start.json

# Extract the session ID
SESSION_ID=$(python3 -c "import json,sys; print(json.load(open('/tmp/preview_start.json'))['result']['sessionId'])")
echo "Session ID: $SESSION_ID"

# Send the test utterance (flag is --utterance, not --message; --api-name is required)
sf agent preview send \
  --session-id "$SESSION_ID" \
  --utterance "your test utterance here" \
  --api-name <AgentApiName> \
  -o <org> --json | tee /tmp/preview_response.json

# Extract the agent's response text
# The message type is "Inform" in current API versions -- print all messages regardless of type
python3 -c "
import json
data = json.load(open('/tmp/preview_response.json'))
result = data.get('result', data)
# Response field varies by API version -- try common shapes
for key in ['messages', 'message', 'response']:
    if key in result:
        msgs = result[key] if isinstance(result[key], list) else [result[key]]
        for m in msgs:
            if isinstance(m, dict):
                msg_type = m.get('type', '?')
                msg_text = m.get('message', m.get('text', m))
                print(f'Agent [{msg_type}]: {msg_text}')
        break
else:
    print(json.dumps(result, indent=2))  # fallback: print full result
"

# End the session when done (--api-name is required)
sf agent preview end --session-id "$SESSION_ID" --api-name <AgentApiName> -o <org> --json
```

For multi-turn scenarios (e.g. handoff routing), repeat the `send` step for each follow-up utterance before ending the session.

### 2.3 Classify each scenario

Run each test scenario **3 times** (start a new session each run) and classify:

| Verdict | Criteria |
|---|---|
| `[CONFIRMED]` | Same failure in 3/3 runs |
| `[INTERMITTENT]` | Failure in 1-2 of 3 runs |
| `[NOT REPRODUCED]` | Passes in 3/3 runs -- re-examine Phase 1 evidence |

### 2.4 Record results

For each scenario, record before proceeding to Phase 3:

```
Scenario: <issue type from Phase 1>
Test message: "<exact utterance sent>"
Expected: <topic name / action name / response behavior>
Actual:   <observed topic / action / verbatim response>
Verdict:  [CONFIRMED] / [INTERMITTENT] / [NOT REPRODUCED]
```

Only `[CONFIRMED]` and `[INTERMITTENT]` issues proceed to Phase 3.

---

## Phase 3: Improve -- Edit .agent File Directly

Phase 3 edits the `.agent` file directly using the Edit tool. No intermediate markdown conversion step. After editing, validate and publish the authoring bundle.

### 3.1 Understand the .agent file structure

The `.agent` file uses Agent Script -- a tab-indented DSL that compiles to Agentforce metadata. Key sections:

```
system:
    instructions: "Agent-level system prompt (persona, guardrails)"
    messages:
        welcome: "Welcome message"
        error: "Error fallback message"

config:
    agent_name: "AgentApiName"
    agent_label: "Agent Display Name"
    description: "Agent description"
    default_agent_user: "user@org.com"

variables:
    myVar: mutable string
        description: "Variable description"
        default: ""

start_agent: entry_topic

topic entry_topic:
    label: "Entry Topic"
    description: "Routes users to specialized topics"  # -> GenAiPluginDefinition.Description (topic routing)

    reasoning:
        instructions: ->                                # -> GenAiPluginInstructionDef.Instruction (LLM prompt)
            | Welcome the user warmly.
            | Ask how you can help today.
        actions:
            go_to_orders: @utils.transition to @topic.orders
                description: "Route to orders topic"
            check_order: @actions.get_order_status
                description: "Look up order details"
                with order_id = @variables.order_id       # input binding
                set @variables.order_status = @outputs.status  # output capture
```

**Critical mapping to Salesforce metadata:**
- `topic.description` -> `GenAiPluginDefinition.Description` (topic routing signal -- determines when the LLM routes to this topic)
- `topic.reasoning.instructions` -> `GenAiPluginInstructionDef.Instruction` (verbatim LLM prompt text injected when topic is active)
- `system.instructions` -> `GenAiPlannerDefinition.Description` (agent-level system prompt)
- `reasoning.actions` with `@utils.transition` -> topic transitions
- `reasoning.actions` with `@actions.*` -> action invocations with `with` (input) and `set` (output) bindings

This mapping is what Phase 1.5b verifies by reading the retrieved `.agent` file -- the fix closes the gap between what's in the file and what's deployed.

### 3.2 Map issue to fix location

| Root cause category | STDM signal | Fix target in .agent file | What to change |
|---|---|---|---|
| `Agent Configuration Gap` | Topic misroute | `topic <name>: description:` | Tighten description to exclude overlapping intents |
| `Agent Configuration Gap` | Action not called | `topic <name>: reasoning: actions:` and `reasoning: instructions:` | Add action definition under `actions:` and mention it in `instructions:` |
| `Agent Configuration Gap` | Wrong action input / error | `reasoning: actions: <action>: with` | Correct `with` bindings or action `target:` URI. Target URI format: `flow://FlowApiName`, `apex://ClassName`, `retriever://RetrieverName` -- type prefix must be lowercase |
| `Agent Configuration Gap` | Variable not captured | `reasoning: actions: <action>: set` | Add `set @variables.myVar = @outputs.field` binding |
| `Agent Configuration Gap` | No post-action transition | `reasoning: actions:` | Add `@utils.transition to @topic.<next_topic>` action |
| `Agent Configuration Gap` | LOW adherence / vague instructions | `topic <name>: reasoning: instructions:` | Rewrite using current `.agent` file instructions as baseline -- see instruction principles below |
| `Agent Configuration Gap` | Identical instructions across topics | All `topic: reasoning: instructions:` blocks | Give each topic distinct, actionable instructions |
| `Knowledge Gap -- Infrastructure` | Knowledge question answered generically | Add knowledge action definition to the relevant topic | Define action with `retriever://` target |
| `Knowledge Gap -- Content` | Knowledge question -- wrong/missing answer | N/A (org data issue) | Add missing articles to knowledge space; verify `DataKnowledgeSrcFileRef` |
| `Platform / Runtime Issue` | Action timeout / latency > 10s | Flow or Apex class (not .agent) | Optimize query/processing logic; add timeout handling |

**When fixing topic instructions**, always quote the current instruction from the `.agent` file before proposing a replacement:

```
Current instruction (from .agent file, topic: <topic_name>):
> <verbatim reasoning: instructions: content>

Proposed replacement:
> <new instruction text>
```

### 3.3 Principles for effective topic instructions

Good instructions are specific, imperative, and action-named. Poor instructions are persona descriptions or generic guidance reused across topics.

1. **Name the action explicitly** -- "Use `@actions.schedule_test_drive` to book the appointment" not "help the user book"
2. **State the pre-condition** -- "Only handle scheduling after the customer's name and email have been collected"
3. **State what to do after** -- "After scheduling completes, confirm the date/time and transition to follow_up"
4. **Scope tightly** -- "This topic handles test drive scheduling only. For vehicle specs or pricing, do not answer -- the user should be routed to general_support"
5. **Keep persona out of instructions** -- persona belongs in `system: instructions:` (agent-level), not per-topic reasoning instructions
6. **One responsibility per topic** -- if the instruction covers 3 distinct tasks, split into 3 topics

**Before / after example** (identical instructions -> distinct instructions):

*Before (generic persona text, same across all topics):*
```
reasoning:
    instructions: |
        You are Nova, a friendly Tesla support assistant. Greet customers warmly,
        help them with their needs, and guide them toward scheduling a test drive.
```

*After (for `identity_collection` topic specifically):*
```
reasoning:
    instructions: ->
        | Collect the customer's name, email address, and phone number using @actions.collect_customer_info.
        | Do not proceed until all three fields are provided.
        | After collection, confirm the details back to the customer.
    actions:
        collect_info: @actions.collect_customer_info
            description: "Capture customer contact details"
            set @variables.customer_name = @outputs.name
            set @variables.customer_email = @outputs.email
        proceed: @utils.transition to @topic.schedule_test_drive
            description: "Move to test drive scheduling after info collected"
            available when @variables.customer_name != ""
```

### 3.4 Regression Prevention

When editing topic instructions, follow these principles to avoid regressions:

1. **Establish a baseline BEFORE editing** — Run the test utterance 3 times before
   making changes. Record the pass rate. This is your baseline.

2. **Make minimal, targeted edits** — Change only the specific instruction line that
   addresses the identified issue. Do NOT expand terse instructions into verbose ones
   unless the terse version was causing a specific documented failure.

3. **Avoid instruction expansion** — Adding more text to instructions does NOT always
   help. The LLM may over-interpret verbose instructions and skip asking the user for
   needed input. Prefer:
   - Adding a single action reference: "Use `@actions.X` to look up..."
   - Adding a single constraint: "Do not proceed until the customer provides..."
   - Adding a single routing directive: "After completing, transition to @topic.Y"

4. **Test immediately after each edit** — Run the same test utterances. If pass rate
   drops, revert the change immediately. Use `git diff` to see exactly what changed.

5. **One fix per publish cycle** — Do not batch multiple instruction changes into a
   single publish. Fix one issue, verify, then move to the next.

### 3.5 Apply fixes

**Step 1 -- Read the current .agent file:**

Use the Read tool to read `AGENT_FILE` (the path resolved in the Routing section). Locate the specific `topic` block that needs changes.

```bash
# Confirm the .agent file exists
ls <AGENT_FILE>
```

**Step 2 -- Edit the .agent file directly:**

Use the Edit tool to make targeted changes. Edit only the specific lines that need to change -- do not rewrite the entire file. Common edit patterns:

**Editing topic description (for topic misroute fixes):**
```
# Find and replace the topic's description line
topic orders:
    description: "Handle order status and tracking inquiries"
```

**Editing topic instructions (for LOW adherence / vague instruction fixes):**
```
# Replace the reasoning instructions block
    reasoning:
        instructions: ->
            | <new instruction line 1>
            | <new instruction line 2>
```

**Adding an action to a topic:**
```
# Add action definition under reasoning: actions:
        actions:
            new_action: @actions.action_api_name
                description: "What this action does"
                with param_name = @variables.source_var
                set @variables.target_var = @outputs.output_field
```

**Adding a transition action:**
```
            go_to_next: @utils.transition to @topic.next_topic
                description: "Route to next topic after completing this task"
```

**Adding an `available when` guard:**
```
            sensitive_action: @actions.do_sensitive_thing
                description: "Only available after verification"
                available when @variables.customer_verified == True
```

IMPORTANT: Agent Script uses **tabs** for indentation, not spaces. Preserve the existing indentation style when editing.

**Step 3 -- Show the diff:**

After editing, show the before/after diff of the changed section so the user can review:

```bash
# If using git, show the diff
cd <project-root> && git diff <AGENT_FILE>
```

### 3.6 Validate, Deploy, Publish, and Activate

After editing the `.agent` file, use this deployment chain to push changes to the live agent. **Never update `GenAiPluginInstructionDef` or other agent metadata directly** -- always edit the `.agent` file and re-deploy. The `.agent` file is the single source of truth.

```bash
# Step 1: Validate (dry run -- checks for syntax errors, no changes to org)
sf agent validate authoring-bundle --api-name <AGENT_API_NAME> -o <org> --json
```

If validation fails, read the error output carefully:
- **Syntax errors** -- fix the `.agent` file (usually indentation or missing required fields)
- **Missing targets** -- the action references a Flow/Apex/Retriever that doesn't exist in the org. Deploy the target first or remove the action.
- **Duplicate names** -- two actions or topics share the same API name

```bash
# Step 2: Publish (compiles Agent Script, deploys metadata, and activates the agent)
sf agent publish authoring-bundle --api-name <AGENT_API_NAME> -o <org> --json
```

A successful publish returns a JSON result with `status: "Success"`. The agent is now live with the updated configuration.

**If publish fails** (common with agents that have many versions or orphaned drafts), use the deploy + activate fallback:

```bash
# Step 3a: Deploy the bundle to the metadata store
sf project deploy start --metadata "AiAuthoringBundle:<AGENT_API_NAME>" -o <org>

# Step 3b: Activate the agent (creates a new active version from the deployed bundle)
sf agent activate --api-name <AGENT_API_NAME> -o <org>
```

> **Important:** `sf project deploy start` stores the bundle but does NOT always propagate instruction changes to live `GenAiPluginInstructionDef` records. The `sf agent activate` step is required to create an active version. If instructions still don't match after deploy + activate, try publish again -- the deploy may have resolved the underlying metadata conflict.

**Verification after deploy:**

Always verify by running a quick preview test (not by querying BPO objects):

```bash
# Quick smoke test to verify the deploy took effect
sf agent preview start --api-name <AgentApiName> -o <org> --json | tee /tmp/deploy_verify_start.json
SESSION_ID=$(python3 -c "import json; print(json.load(open('/tmp/deploy_verify_start.json'))['result']['sessionId'])")

sf agent preview send \
  --session-id "$SESSION_ID" \
  --utterance "<utterance that exercises the changed topic>" \
  --api-name <AgentApiName> \
  -o <org> --json | tee /tmp/deploy_verify_response.json

sf agent preview end --session-id "$SESSION_ID" --api-name <AgentApiName> -o <org> --json
```

If the agent still exhibits old behavior after deploy + activate, the publish did not fully propagate -- try `sf agent publish authoring-bundle` again, or re-run deploy + activate.

**Never use the Tooling API to patch `GenAiPluginInstructionDef` or other BPO objects directly.** This creates drift between the `.agent` file (source of truth) and the live metadata. Always fix the `.agent` file and re-deploy.

### 3.7 Verify

**Immediate** -- run the Phase 2 scenarios that returned `[CONFIRMED]` before the fix. All should now return `[NOT REPRODUCED]`.

```bash
# Quick smoke test after publish
sf agent preview start --api-name <AgentApiName> -o <org> --json | tee /tmp/verify_start.json
SESSION_ID=$(python3 -c "import json; print(json.load(open('/tmp/verify_start.json'))['result']['sessionId'])")

sf agent preview send \
  --session-id "$SESSION_ID" \
  --utterance "<test utterance from Phase 2 scenario>" \
  --api-name <AgentApiName> \
  -o <org> --json | tee /tmp/verify_response.json

sf agent preview end --session-id "$SESSION_ID" --api-name <AgentApiName> -o <org> --json
```

**At scale** -- after 24-48 hours of new live sessions, re-run Phase 1 over the new date range and compare against the pre-fix baseline:

| Metric | What to look for after fix |
|---|---|
| Topics seen in STDM | Dead topics should now appear in session data |
| `TRUST_GUARDRAILS_STEP` value | `LOW` occurrences should drop or disappear |
| Action invocation per turn | Actions should now fire for the intents they cover |
| `action_error_count` | Should not increase (regression check) |
| Avg session duration / turn count | Shorter = less confusion, faster resolution |

If new issues surface in the post-fix Phase 1 run, repeat the cycle from Phase 1.4.

### 3.8 Update Testing Center test cases (cross-skill with adlc-test)

After fixing issues, create or update test cases in **Testing Center format** so they can be deployed directly to the org via `sf agent test create`. This ensures regressions are caught automatically.

**Step 1 -- Derive test cases from confirmed issues:**

For each `[CONFIRMED]` or `[INTERMITTENT]` issue from Phase 2, create a test case in Testing Center YAML format:

```yaml
# tests/<AgentApiName>-regression.yaml
name: "<AgentApiName> Regression Tests"
subjectType: AGENT
subjectName: <AgentApiName>

testCases:
  - utterance: "<exact utterance from Phase 2 scenario>"
    expectedTopic: <topic_that_should_handle_this>
    expectedActions:
      - <action_that_should_fire>

  - utterance: "<another failing utterance>"
    expectedTopic: <expected_topic>
    expectedOutcome: "Agent should <expected behavior description>"
```

**Key format rules:**
- `expectedActions` is a **flat string list**: `["action_a"]`, NOT objects
- `subjectName` is the agent's `DeveloperName` (API name without `_vN` suffix)
- `expectedOutcome` uses LLM-as-judge evaluation -- describe the desired behavior in natural language
- If a test case only needs topic routing validation, omit `expectedActions`

**Step 2 -- Write the test file:**

```bash
mkdir -p <project-root>/tests
# Write tests/<AgentApiName>-regression.yaml
```

If a regression file already exists, append new test cases to the existing `testCases` array.

**Step 3 -- Deploy and run tests via Testing Center:**

```bash
# Deploy the test suite to the org
sf agent test create \
  --spec tests/<AgentApiName>-regression.yaml \
  --api-name <AgentApiName>_Regression \
  --force-overwrite \
  -o <org> --json

# Run and wait for results
sf agent test run \
  --api-name <AgentApiName>_Regression \
  --wait 10 \
  --result-format json \
  -o <org> --json | tee /tmp/regression_run.json

# Get results (ALWAYS use --job-id, NOT --use-most-recent which is broken)
JOB_ID=$(python3 -c "import json; print(json.load(open('/tmp/regression_run.json'))['result']['runId'])")
sf agent test results --job-id "$JOB_ID" --result-format json -o <org> --json
```

Or invoke the adlc-test skill directly: `/adlc-test <org> --api-name <AgentApiName>`

**Step 4 -- Verify all previously-broken scenarios now pass:**

All test cases derived from Phase 2 `[CONFIRMED]` issues should pass after the Phase 3 fix. If any fail, return to Phase 3.4 and iterate.

---

## STDM Reference

### Data hierarchy

```
AiAgentSession (1)
+-- AiAgentSessionParticipant (N)       -- agent planner IDs and user IDs linked to this session
+-- AiAgentInteraction (N)              -- one per conversational turn
    +-- AiAgentInteractionMessage (N)   -- user and agent messages
    +-- AiAgentInteractionStep (N)      -- internal steps (LLM, actions)
```

### Key fields

**AiAgentSession** (`ssot__AiAgentSession__dlm`)
- `ssot__Id__c` -- Session ID
- `ssot__StartTimestamp__c` / `ssot__EndTimestamp__c` -- Session timing -> `session.duration_ms`
- `ssot__AiAgentChannelType__c` -- Channel -> `session.channel`
- `ssot__AiAgentSessionEndType__c` -- How the session ended: `USER_ENDED`, `AGENT_ENDED`, or null -> `session.end_type`
- `ssot__VariableText__c` -- Final variable snapshot for the session -> `session.session_variables`

**AiAgentSessionParticipant** (`ssot__AiAgentSessionParticipant__dlm`)
- `ssot__AiAgentSessionId__c` -- Session this participant belongs to
- `ssot__AiAgentApiName__c` -- API name of the agent (primary filter field -- no SOQL needed)
- `ssot__ParticipantId__c` -- GenAiPlannerDefinition ID (key prefix `16j`) for agents, `005...` for users. May be 15-char or 18-char -- `AgentforceOptimizeService` automatically queries both formats as a fallback.

**AiAgentInteraction** (`ssot__AiAgentInteraction__dlm`)
- `ssot__TopicApiName__c` -- Topic/skill that handled this turn -> `turn.topic`
- `ssot__StartTimestamp__c` / `ssot__EndTimestamp__c` -- Turn timing -> `turn.duration_ms`
- `ssot__TelemetryTraceId__c` -- Distributed tracing ID -> `turn.telemetry_trace_id`

**AiAgentInteractionMessage** (`ssot__AiAgentInteractionMessage__dlm`)
- `ssot__AiAgentInteractionMessageType__c` -- `Input` (user) or `Output` (agent) -> `message.message_type`
- `ssot__ContentText__c` -- Message text -> `message.text`

**AiAgentInteractionStep** (`ssot__AiAgentInteractionStep__dlm`)
- `ssot__AiAgentInteractionStepType__c` -- `TOPIC_STEP`, `LLM_STEP`, `ACTION_STEP`, `SESSION_END`, `TRUST_GUARDRAILS_STEP` -> `step.step_type`
- `ssot__Name__c` -- Step or action name -> `step.name`
- `ssot__ErrorMessageText__c` -- Error text (null if none) -> `step.error`
- `ssot__InputValueText__c` / `ssot__OutputValueText__c` -- Input/output data -> `step.input` / `step.output`
- `ssot__PreStepVariableText__c` / `ssot__PostStepVariableText__c` -- Variable snapshots -> `step.pre_vars` / `step.post_vars`
- `ssot__GenerationId__c` -- Links to `GenAIGeneration__dlm` -> `step.generation_id` (non-null on LLM_STEP)
- `ssot__GenAiGatewayRequestId__c` -- Links to `GenAIGatewayRequest__dlm` -> `step.gateway_request_id` (non-null on LLM_STEP)

**Einstein Audit & Feedback DMOs** (joined via `getLlmStepDetails()`)

`GenAIGeneration__dlm` -- LLM generation records:
- `generationId__c` -- Join key to `ssot__GenerationId__c` on the step DMO
- `responseText__c` -- The full LLM response text -> `LlmStepDetail.llm_response`

`GenAIGatewayRequest__dlm` -- Raw gateway requests sent to the LLM:
- `gatewayRequestId__c` -- Join key to `ssot__GenAiGatewayRequestId__c` on the step DMO
- `prompt__c` -- Full prompt text including system instructions -> `LlmStepDetail.prompt`

These two DMOs are only populated when Einstein Audit & Feedback is enabled in the org's Data Cloud setup.

**`TRUST_GUARDRAILS_STEP`** -- A safety/compliance step that measures whether the agent's response followed its instructions:
- `step.name` is typically `InstructionAdherence`
- `step.output` is a Python-style dict string (not JSON). Actual format:
  ```
  {'name': 'InstructionAdherence', 'value': 'HIGH', 'explanation': 'This response adheres to the assigned instructions.'}
  ```
  Check for adherence by searching for `'value': 'LOW'` (or just `LOW`) in the output string.
- `step.input` contains the raw `input_text` and `output_text` that were evaluated, e.g.:
  ```
  input_text: <user message>, output_text: <agent response>
  ```
- `step.error` may contain the literal string `"None"` (not a real error -- see Data quality below)
- Does **not** count toward `action_error_count` (the Apex class only counts errors on `ACTION_STEP` type)

### Data quality

**`NOT_SET` sentinel.** Data Cloud uses `"NOT_SET"` for null/absent values. `AgentforceOptimizeService` strips this sentinel -- any field returning `null` in the JSON should be treated as absent.

**`TRUST_GUARDRAILS_STEP` error field.** `TRUST_GUARDRAILS_STEP` steps may have the Python string `"None"` in their `error` field (not `"NOT_SET"`). This is **not** a real error -- treat it as absent. `action_error_count` is only incremented for `ACTION_STEP` errors so this sentinel does not inflate the count.

**Null `end_time` / `duration_ms`.** Sessions and turns may have `null` for `end_time` and therefore `null` for `duration_ms` when no session-end event was recorded by Data Cloud. This is common and does not indicate a problem -- just treat duration as unknown for those sessions.

**`LLM_STEP` input/output format.** The `input` and `output` fields on `LLM_STEP` contain raw Python dict strings (the internal LlamaIndex representation), not valid JSON. They are useful for confirming what was sent to the LLM but are not machine-parseable. Example:
```
{'current_agent_name': 'entry', 'messages': [ChatMessage(role=<MessageRole.SYSTEM: 'system'>, ...)]}
```
Do not attempt to `JSON.parse()` these values. Only `ACTION_STEP` input/output is structured JSON.

**Participant ID format inconsistency.** The `ssot__AiAgentSessionParticipant__dlm` DMO stores `ssot__ParticipantId__c` as either 15-char or 18-char Salesforce IDs, inconsistently across sessions and orgs. `AgentforceOptimizeService.resolvePlannerIds()` automatically adds both the 18-char (from SOQL) and 15-char (substring) versions to the IN clause to handle this.

### Data Space name

Always run Phase 0 first to discover the correct Data Space `name` for the org. Use `sf api request rest "/services/data/v66.0/ssot/data-spaces" -o <org>` (no `--json` flag -- unsupported on this beta command). Never assume `'default'` without checking -- it is only a fallback if the API call fails. If STDM queries return zero rows after confirming the Data Space, direct the user to Salesforce Setup -> Data Cloud -> Data Spaces to verify the name.

---

## Agent Name Resolution Reference

The only Salesforce metadata object that should be queried directly is `GenAiPlannerDefinition` -- used exclusively for agent name resolution in the Routing step.

| Object | Purpose | When to query |
|---|---|---|
| `GenAiPlannerDefinition` | The agent definition | Routing step only -- to resolve `MasterLabel`, `DeveloperName`, and `Id` |
| `DataKnowledgeSpace` | Knowledge base container | Phase 1.5b Step 5 only -- if knowledge gaps are detected |

**Do NOT query these objects directly** -- use the `.agent` file instead:
- `GenAiPluginDefinition` (topics) -- read from `.agent` file `topic:` blocks
- `GenAiPluginInstructionDef` (instructions) -- read from `.agent` file `reasoning: instructions:` blocks
- `GenAiFunction` (actions) -- read from `.agent` file `reasoning: actions:` blocks

The `.agent` file is the single source of truth. All fixes should be applied to it and deployed via the Phase 3.5 deployment chain.
