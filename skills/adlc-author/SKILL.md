---
name: adlc-author
description: Generate Agentforce Agent Script (.agent) files directly from requirements
allowed-tools: Bash Read Write Edit Glob Grep
argument-hint: "[describe your agent] | review <path/to/file.agent>"
---

# ADLC Author Skill

This skill writes `.agent` files DIRECTLY from natural language requirements. There is no
intermediate markdown, no Python converter, no code generation pipeline. Claude reads the
requirements, asks clarifying questions, then writes a valid `.agent` file using the Write
tool. A PostToolUse hook auto-validates every Write to an `.agent` file.

---

## 1. OVERVIEW

### What This Skill Does

Given a description of an Agentforce agent, this skill:
0. Reviews the request for safety and responsible AI compliance
1. Gathers requirements through targeted questions
2. Queries the target org for the Einstein Agent User
3. Generates a complete `.agent` file using Agent Script DSL
4. Creates the companion `bundle-meta.xml`
5. Validates the output via CLI
6. Presents a 100-point quality score (including 15-point safety category)
7. Runs a live preview session with trace analysis to verify behavior
8. Deploys (publish + activate) when the agent is confirmed working

### When to Use This Skill

- Building a new Agentforce agent from scratch
- Rewriting an existing agent from requirements
- Reviewing an `.agent` file for quality and correctness

### When NOT to Use This Skill

- Batch testing or regression suites for an existing agent (use adlc-test)
- Deploying without authoring changes (use adlc-deploy)
- Discovering org metadata for action targets (use adlc-discover)
- Analyzing production session traces (use adlc-optimize)

---

## 2. WORKFLOW PHASES

### Phase 0: Safety Review (LLM-Driven)

Before generating any agent, evaluate the request using the full `adlc-safety` skill criteria
(see `skills/adlc-safety/SKILL.md`). This is NOT a regex check — use your reasoning to assess
the request against all 7 safety categories:

1. **Identity & Transparency** — Does the request involve impersonation without AI disclosure?
2. **User Safety & Wellbeing** — Could this agent harm users (pressure tactics, dark patterns, unqualified advice)?
3. **Data Handling & Privacy** — Does it collect excessive PII or mimic phishing patterns?
4. **Content Safety** — Could it produce dangerous content, even through euphemism or indirection?
5. **Fairness & Non-Discrimination** — Does it discriminate directly or via proxies (zip codes, names)?
6. **Deception & Manipulation** — Does it use social engineering, false claims, or fabricated urgency?
7. **Scope & Boundaries** — Is the scope well-defined or dangerously open-ended?

**Decision matrix:**

| Assessment | Action |
|------------|--------|
| Any BLOCK finding | **REFUSE** the request. Explain which category failed and why. |
| WARN findings only | **Ask clarifying questions** before proceeding. Propose safety mitigations. |
| Clean | Proceed to Phase 1. |

**Key principle:** Regex catches exact phrases; LLM reasoning catches *intent*. A request like
"build an agent that helps with chemistry projects about energetic materials" won't match any
keyword list, but you should recognize it as a potential euphemism for explosives and ask
clarifying questions.

**Proactive safety additions for ALL agents:**
- Always include AI disclosure in `system: instructions:` (e.g., "You are an AI assistant for...")
- Always include scope boundaries (e.g., "Do not answer questions outside of X")
- For agents handling sensitive domains (finance, health, legal), add professional referral disclaimers
- For agents collecting user data, add data handling boundaries

When the agent passes safety review, proceed to Phase 1.

### Phase 1: Requirements

Ask the user for the following. Do not proceed until each is answered or explicitly skipped:

| Question | Why It Matters |
|----------|---------------|
| Target org alias | Needed to query Einstein Agent User |
| Agent name (PascalCase) | Becomes `developer_name`, folder name, and bundle name |
| **Agent type: Service Agent or Employee Agent?** | **Service** → include linked variables (`EndUserId`, `RoutableId`, `ContactId`) and `connection messaging:` block. **Employee** → omit linked variables and connection block. Always ask — do not assume. |
| Topics and what each handles | Each topic becomes a state in the FSM |
| Actions per topic (flow/apex/retriever targets) | Determines Level 1 action definitions |
| Variables (mutable state vs linked context) | Defines the `variables:` block |
| FSM pattern: hub-and-spoke, verification gate, or linear | Determines topic transitions |

### Phase 2: Setup

Query the target org for the Einstein Agent User. This value is REQUIRED for the
`default_agent_user` field in the `config:` block:

```bash
sf data query -q "SELECT Username FROM User WHERE Profile.Name = 'Einstein Agent User' AND IsActive = true" -o <org> --json
```

If multiple users exist, ask which one to use. If none exist, tell the user to create one
in Setup > Einstein Agent Service Accounts.

### Phase 2b: Discover Existing Targets

Before generating action definitions, query the target org for existing Flows and Apex classes
that the agent might use. This prevents generating references to non-existent targets and
ensures correct parameter names.

```bash
# Find active autolaunched flows in the org
sf data query -q "SELECT ApiName, IsActive, Description FROM FlowDefinitionView WHERE IsActive = true AND ProcessType = 'AutoLaunchedFlow'" -o <org> --json

# For each candidate flow, check its actual input/output parameters
sf api request rest "/services/data/v63.0/actions/custom/flow/<FlowApiName>" -o <org>
```

NOTE: `FlowDefinitionView` does NOT have a `Status` column. Use `IsActive` (boolean):
```bash
# WRONG: Status column doesn't exist
sf data query -q "SELECT ApiName, Status FROM FlowDefinitionView" -o <org> --json

# CORRECT: Use IsActive
sf data query -q "SELECT ApiName, IsActive FROM FlowDefinitionView WHERE IsActive = true" -o <org> --json
```

The REST endpoint returns the exact input/output parameter schema:
```json
{
  "inputs": [
    { "name": "customerId", "type": "STRING", "required": true }
  ],
  "outputs": [
    { "name": "caseId", "type": "STRING" }
  ]
}
```

**Use the discovered parameters** in the Level 1 action definition's `inputs:` and `outputs:`
blocks. Do NOT guess parameter names.

If no suitable existing targets are found, generate action definitions with descriptive
target names (e.g., `flow://ATT_Check_Area_Outage`). These will need to be scaffolded
by adlc-scaffold before deployment.

### Phase 3: Generate

Write the `.agent` file and bundle metadata to the standard bundle directory:

```
force-app/main/default/aiAuthoringBundles/<AgentName>/
  <AgentName>.agent
  <AgentName>.bundle-meta.xml
```

Use the Write tool for both files. The bundle-meta.xml MUST be minimal — only `bundleType`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<AiAuthoringBundle xmlns="http://soap.sforce.com/2006/04/metadata">
  <bundleType>AGENT</bundleType>
</AiAuthoringBundle>
```

CRITICAL: Do NOT add `<developerName>`, `<masterLabel>`, `<description>`, `<target>`, or any
other fields. The publish command (`sf agent publish authoring-bundle`) manages these
automatically. Extra fields cause "Required fields are missing: [BundleType]" deploy errors
because the Metadata API deploy step fails when unexpected fields are present.

### Phase 4: Validate

The PostToolUse hook auto-validates on Write. Additionally, run the CLI validator:

```bash
sf agent validate authoring-bundle --api-name <AgentName> -o <org> --json
```

Before running the CLI validator, manually verify:
- [ ] Every `@actions.X` reference in `reasoning > actions:` has a corresponding `X:` definition in `topic > actions:`
- [ ] Every Level 1 action has `target:`, `inputs:`, and `outputs:`
- [ ] Indentation is consistent throughout (tab-indented)

If validation fails, read the error output, fix the `.agent` file, and re-validate.

### Phase 5: Review

Run the `adlc-safety` review against the generated `.agent` file. Read the file and evaluate
it against all 7 safety categories from `skills/adlc-safety/SKILL.md`. Include the safety
findings in the 100-point score breakdown (see Section 6 — Safety & Responsible AI: 15 points).

### Phase 6: Preview & Test

After validation passes, run a live preview session to verify the agent works end-to-end. Use `--authoring-bundle` to compile from the local `.agent` file and generate trace files for diagnosis.

**Prerequisites:** The agent must be published at least once before preview will work:
```bash
sf agent publish authoring-bundle --api-name <AgentName> -o <org> --json
```

**Run the preview loop:**
```bash
# Start session (--authoring-bundle compiles local .agent file + generates traces)
SESSION_ID=$(sf agent preview start \
  --authoring-bundle <AgentName> \
  --target-org <org> --json 2>/dev/null \
  | jq -r '.result.sessionId')

# Send a test utterance per topic
for UTT in "utterance for topic 1" "utterance for topic 2" "off-topic test"; do
  echo "--- Sending: $UTT ---"
  RESPONSE=$(sf agent preview send \
    --session-id "$SESSION_ID" \
    --authoring-bundle <AgentName> \
    --utterance "$UTT" \
    --target-org <org> --json 2>/dev/null)

  # Show response
  echo "$RESPONSE" | jq -r '.result.messages[0].message'

  # Capture planId for trace analysis
  PLAN_ID=$(echo "$RESPONSE" | jq -r '.result.messages[-1].planId')
  echo "Plan ID: $PLAN_ID"
done

# End session
sf agent preview end \
  --session-id "$SESSION_ID" \
  --authoring-bundle <AgentName> \
  --target-org <org> --json 2>/dev/null
```

**Trace file location:**
```
.sfdx/agents/<AgentName>/sessions/<sessionId>/
  metadata.json          # session metadata (agentId, startTime, mockMode)
  transcript.jsonl       # full conversation (role, text, raw messages per turn)
  traces/<planId>.json   # execution trace per turn (topic routing, actions, LLM prompts)
```

**Inspect traces for issues:**
```bash
TRACE=".sfdx/agents/<AgentName>/sessions/$SESSION_ID/traces/$PLAN_ID.json"

# Which topic handled the turn?
jq -r '.topic' "$TRACE"

# Which actions were available?
jq -r '.plan[] | select(.type == "BeforeReasoningIterationStep") | .data.action_names[]' "$TRACE"

# Was the response grounded?
jq -r '.plan[] | select(.type == "ReasoningStep") | {category, reason}' "$TRACE"

# What prompt did the LLM receive?
jq -r '.plan[] | select(.type == "LLMStep") | .data.messages_sent[0].content' "$TRACE" | head -50
```

**Fix loop (max 3 iterations):**

If trace analysis reveals issues (wrong topic, missing action, ungrounded response):
1. Edit the `.agent` file to fix the issue (expand topic description, relax action guards, add instruction detail)
2. Re-run preview — `--authoring-bundle` picks up local changes immediately, no re-publish needed
3. Check traces again to confirm the fix

| Trace symptom | Likely cause | Fix |
|---------------|-------------|-----|
| Wrong topic in `.topic` | Topic description too vague | Add keywords from the utterance |
| Action missing from enabled tools | `available when` guard too restrictive | Relax or remove the guard |
| `"category": "UNGROUNDED"` | Instructions lack data references | Add `{!@variables.x}` references |
| `topic: "DefaultTopic"` | No topic matched | Add keywords to topic descriptions |
| Only `__state_update_action__` in action list | Topic has no actions | Add `reasoning: actions:` block |

### Phase 7: Deploy

Once preview confirms the agent works correctly:

#### Step 1: Check action targets exist

Before publishing, verify all flow/apex targets referenced in the `.agent` file exist in the org. Publishing will fail if any target is missing.

```bash
# Parse flow targets from the .agent file
grep -o 'flow://[A-Za-z0-9_]*' force-app/main/default/aiAuthoringBundles/<AgentName>/<AgentName>.agent | sort -u

# Parse apex targets
grep -o 'apex://[A-Za-z0-9_]*' force-app/main/default/aiAuthoringBundles/<AgentName>/<AgentName>.agent | sort -u

# For each flow target, check if it exists and is active
sf data query -q "SELECT ApiName FROM FlowDefinitionView WHERE ApiName = '<FlowApiName>' AND IsActive = true" -o <org> --json

# For each apex target, check if it exists
sf data query -q "SELECT Name FROM ApexClass WHERE Name = '<ClassName>' AND Status = 'Active'" -o <org> --json
```

If targets are missing, scaffold and deploy them **before** publishing:

```bash
# Option A: Use adlc-scaffold to generate stubs
# python3 scripts/scaffold.py --agent-file <path> -o <org> --output-dir force-app/main/default

# Option B: Manually create stubs (flows/apex) then deploy
sf project deploy start --source-dir force-app/main/default/flows -o <org> --json
sf project deploy start --source-dir force-app/main/default/classes -o <org> --json
```

Do NOT attempt `sf agent publish` until all targets exist — it will fail with "Invocable action does not exist".

#### Step 2: Publish and activate

```bash
# Publish (compiles .agent into org metadata)
sf agent publish authoring-bundle --api-name <AgentName> -o <org> --json

# Activate (makes agent available to end users)
sf agent activate --api-name <AgentName> -o <org>
```

Tell the user: "Agent published and activated. You can now test it in the Agent Builder UI or via the messaging channel."

If the user doesn't want to deploy yet, skip this phase and remind them to run `/adlc-deploy` when ready.

---

## 3. AGENT SCRIPT SYNTAX REFERENCE

This section contains the complete Agent Script DSL syntax. It is self-contained:
you should not need any external reference document for common agent authoring tasks.

### 3.1 Block Structure (Required Order)

```
config:           # 1. REQUIRED: Agent metadata
variables:        # 2. Optional: Mutable state and linked context
system:           # 3. REQUIRED: Global instructions and messages
connection messaging:  # 4. Optional: Escalation routing (service agents)
knowledge:        # 5. Optional: Knowledge base config
language:         # 6. Optional: Locale settings
start_agent <name>:  # 7. REQUIRED: Entry point block (exactly one)
topic:            # 8. REQUIRED: Conversation topics (one or more)
```

### 3.1b Indentation

Agent Script is whitespace-delimited. The parser is generally forgiving — both spaces and tabs work.
The official docs recommend 3-space indentation, but some server versions reject spaces.
**Use tabs** as the safest default that works across all versions.

```
# Level 0 (no indent)
config:
	# Level 1 (1 tab)
	developer_name: "MyAgent"

topic my_topic:
	# Level 1
	description: "Topic description"

	actions:
		# Level 2 (2 tabs)
		my_action:
			# Level 3 (3 tabs)
			description: "Action description"
			target: "flow://My_Flow"
			inputs:
				# Level 4 (4 tabs)
				param: string
					# Level 5 (5 tabs)
					description: "Parameter"
```

**CRITICAL:** Before generating, read any existing `.agent` file in the project to match
its indentation style exactly:

```bash
# Check existing agent file indentation
find force-app -name "*.agent" -exec head -20 {} \;
```

If no existing file, default to tab indentation.

### 3.2 Config Block

The `config:` block defines agent metadata. Field names are exact -- do not substitute.

```
config:
	developer_name: "MyAgent"
	agent_label: "My Agent"
	description: "What this agent does"
	default_agent_user: "einsteinagent@00dxx000001234.ext"
```

| Field | Required | Notes |
|-------|----------|-------|
| `developer_name` | Yes | MUST match the folder name (case-sensitive) |
| `agent_label` | Yes | Human-readable display name |
| `description` | Yes | Agent purpose (used for routing) |
| `default_agent_user` | Yes | Must be a valid Einstein Agent User in the target org |

**NOTE on `agent_type`:** Technically supported (`"AgentforceServiceAgent"` or `"AgentforceEmployeeAgent"`). Include it when the user specifies an agent type — it works on current server versions. If publish fails with a null pointer crash (seen on older versions), remove it and set the type via Setup UI after publish. Always ask the user which type they want (see Phase 1) to determine linked variables and connection block.

CRITICAL: `developer_name` must exactly match the folder name under `aiAuthoringBundles/`.
If the folder is `AcmeAgent`, the `developer_name` must be `"AcmeAgent"`.

### 3.3 Variables Block

Variables define agent state. Two modifiers exist:

#### Mutable Variables (read-write state)
```
variables:
	order_id: mutable string = ""
		description: "Current order being discussed"
	is_verified: mutable boolean = False
		description: "Whether customer has been verified"
	attempt_count: mutable number = 0
		description: "Number of verification attempts"
```

#### Linked Variables (read-only context)
```
variables:
	EndUserId: linked string
		source: @MessagingSession.MessagingEndUserId
		description: "Messaging End User ID"
		visibility: "External"
	RoutableId: linked string
		source: @MessagingSession.Id
		description: "Messaging Session ID"
		visibility: "External"
	ContactId: linked string
		source: @MessagingEndUser.ContactId
		description: "Contact ID"
		visibility: "External"
```

NOTE: `visibility: "External"` is recommended on linked variables for service agents.
It ensures the variable is accessible to the messaging channel.

#### Variable Type Reference

| Type | Mutable | Linked | Action I/O | Default Format |
|------|---------|--------|-----------|---------------|
| `string` | Yes | Yes | Yes | `""` |
| `number` | Yes | Yes | Yes | `0` |
| `boolean` | Yes | Yes | Yes | `False` |
| `object` | Yes | NO | Yes | `{}` |
| `date` | Yes | Yes | Yes | `2025-01-15` |
| `timestamp` | Yes | Yes | Yes | `2025-01-15T10:30:00Z` |
| `currency` | Yes | Yes | Yes | `0` |
| `id` | Yes | Yes | Yes | `""` |
| `list[T]` | Yes | NO | Yes | `[]` |
| `datetime` | NO | NO | Yes | N/A (action params only) |
| `time` | NO | NO | Yes | N/A (action params only) |
| `integer` | NO | NO | Yes | N/A (action params only) |
| `long` | NO | NO | Yes | N/A (action params only) |

Rules:
- Mutable variables MUST have an inline default value (e.g., `= ""`) or default to `None`
- Linked variables MUST have a `source:` and CANNOT have an inline default
- Linked variables CANNOT use `object` or `list` types
- Linked variables support: `string`, `number`, `boolean`, `date`, `timestamp`, `currency`, `id`
- Use `timestamp` instead of `datetime` for mutable date+time variables
- Use `number` instead of `integer`/`long` for mutable numeric variables
- Service agents auto-add `EndUserId`, `RoutableId`, `ContactId` as linked variables
- The `...` token is for slot-filling only (in `with param=...`), never as a default

### 3.4 System Block

```
system:
	instructions: "Global instructions that apply across all topics."
	messages:
		welcome: "Hello! How can I help you today?"
		error: "Something went wrong. Please try again."
```

The `instructions:` value can be a single-line string or a multi-line block using `|`:
```
system:
	instructions: |
		You are a customer service agent for Acme Corp.
		Be professional, concise, and helpful.
		Never disclose internal policies to customers.
```

Topics can override the agent-level `system:` with their own topic-level `system:` block.

### 3.5 Connection Block (Service Agents Only)

```
connection messaging:
	adaptive_response_allowed: True
```

For escalation routing (with Omni-Channel Flow):
```
connection messaging:
	outbound_route_type: "OmniChannelFlow"
	outbound_route_name: "flow://Route_From_Agent"
	escalation_message: "Connecting you with a specialist."
	adaptive_response_allowed: False
```

NOTE: Use `connection messaging:` (singular). NOT `connections:`. When
`outbound_route_type` is present, ALL three route properties are required.
Valid channel types: `messaging`, `voice`, `web`.

### 3.6 Language Block

```
language:
	default_locale: "en_US"
	additional_locales: ""
	all_additional_locales: False
```

Valid locale codes: `ar, bg, ca, cs, da, de, el, en_AU, en_GB, en_US, es, es_MX, et, fi, fr, fr_CA, he, hi, hr, hu, id, in, it, iw, ja, ko, ms, nl_NL, no, pl, pt_BR, pt_PT, ro, sv, th, tl, tr, vi, zh_CN, zh_TW`. Common mistakes: `ja_JP` → use `ja`, `es_US` → use `es` or `es_MX`.

### 3.7 Knowledge Block

```
knowledge:
	citations_enabled: True
```

### 3.8 Start Agent

Exactly one `start_agent` entry point per agent:
```
start_agent router:
```

This names the entry point that handles the first user message and routes to topics.

**CRITICAL: `start_agent` MUST include `description:`, `reasoning: instructions:`, and `reasoning: actions:`.**
Without `description:`, the compiler errors: "Description is required for all topic blocks."
Without `reasoning:` blocks, the entry point has zero enabled tools after initial routing — the LLM sees only guardrail tools and falls back to `DefaultTopic`. Every `start_agent` needs at minimum:

```
start_agent router:
	description: "Route user requests to the appropriate topic"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions or provide help directly.
			Always use a transition action to route to the correct topic immediately.
			- Order questions → use to_orders
			- Return requests → use to_returns
			Never attempt to help the user yourself. Always route.
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Route to order support"
			to_returns: @utils.transition to @topic.return_support
				description: "Route to returns"
```

**CRITICAL: Router-only instructions.** The `start_agent` instructions MUST explicitly say
"You are a router only. Do NOT answer questions directly. Always use a transition action."
Without this directive, the LLM will attempt to answer the user's question itself instead
of routing to the specialized topic — resulting in SMALL_TALK grounding and the user never
reaching the topic with the actual actions.

A `start_agent` with only a name and no `reasoning:` block will compile but produce an agent that cannot route — all utterances land in `DefaultTopic` with zero actions.

**CRITICAL naming rule:** The `start_agent` name MUST differ from all `topic` names. Both `start_agent` and `topic` blocks create `GenAiPluginDefinition` metadata records — if they share a name, publish fails with `duplicate value found: GenAiPluginDefinition`. This error leaves orphaned metadata that blocks all future publishes until the name collision is fixed.

| Pattern | WRONG | CORRECT |
|---------|-------|---------|
| Hub-and-spoke | `start_agent router:` + `topic router:` (name collision!) | `start_agent hub_router:` + `topic main_menu:` |
| Verification gate | `start_agent entry:` + `topic entry:` (name collision!) | `start_agent gate_router:` + `topic welcome:` |
| Linear | `start_agent greeting:` + `topic greeting:` (name collision!) | `start_agent linear_router:` + `topic greeting:` |

### 3.9 Topic Block

Topics are the states in the agent's finite state machine. Each topic has:

```
topic order_support:
	label: "Order Support"
	description: "Handle order status inquiries and tracking"

	actions:
		# Level 1: Action DEFINITIONS (target, inputs, outputs)
		get_order_status:
			description: "Look up order status by order ID"
			target: "flow://Get_Order_Status"
			inputs:
				order_id: string
					description: "The order ID to look up"
			outputs:
				status: string
					description: "Current order status"
					is_displayable: True
				tracking_number: string
					description: "Shipping tracking number"

	reasoning:
		instructions: ->
			| Help the customer check their order status.
			| Ask for their order number if not already provided.

		actions:
			# Level 2: Action INVOCATIONS (with/set bindings)
			lookup_order: @actions.get_order_status
				description: "Look up order details"
				with order_id = @variables.order_id
				set @variables.order_status = @outputs.status

			back_to_menu: @utils.transition to @topic.topic_selector
				description: "Return to main menu"
```

### 3.10 Two-Level Action System (CRITICAL)

This is the most important concept in Agent Script. Actions have two levels:

#### Level 1: Action Definitions

Located inside `topic > actions:` (at the topic level, NOT inside `reasoning:`).
Defines WHAT the action is:

```
actions:
	create_case:
		description: "Create a support case"
		target: "flow://Create_Support_Case"
		label: "Create Case"
		require_user_confirmation: False
		include_in_progress_indicator: True
		progress_indicator_message: "Creating your case..."
		inputs:
			subject: string
				description: "Case subject"
				is_required: True
			desc_text: string
				description: "Case description"
		outputs:
			case_id: string
				description: "Created case ID"
				is_displayable: True
				is_used_by_planner: True
				filter_from_agent: False
```

Action-level optional properties:
- `label` -- human-readable label (default: auto-generated from name)
- `require_user_confirmation` -- Boolean, ask before executing (default: False)
- `include_in_progress_indicator` -- Boolean, show spinner (default: False)
- `progress_indicator_message` -- message during execution

Input optional properties: `is_required`, `is_user_input`, `label`, `complex_data_type_name`
Output optional properties: `is_displayable`, `is_used_by_planner`, `filter_from_agent`, `label`, `complex_data_type_name`

Target protocols (short name or long name both work):
- `flow://Flow_Api_Name` -- Autolaunched Flow
- `apex://ClassName` -- Apex @InvocableMethod (NO GenAiFunction registration needed)
- `prompt://TemplateName` (or `generatePromptResponse://`) -- Prompt Template
- `externalService://ServiceName.operationName` -- External Service
- `retriever://RetrieverName` -- Knowledge retrieval
- `standardInvocableAction://ActionName` -- Built-in Salesforce action
- `quickAction://ActionName` -- Quick Action
- `api://ApiName` -- REST API
- `apexRest://EndpointName` -- Custom Apex REST endpoint
- `mcpTool://ToolName` -- MCP Tool

I/O schemas (`inputs:` + `outputs:`) are REQUIRED for publish. Omitting them causes
"Internal Error" on deploy.

#### Level 2: Action Invocations

Located inside `topic > reasoning > actions:`. Defines HOW to call the action:

```
reasoning:
	actions:
		create_new_case: @actions.create_case
			description: "Create a new support case"
			with subject = @variables.case_subject
			with desc_text = @variables.case_description
			set @variables.case_id = @outputs.case_id
```

Key rules for Level 2:
- Reference Level 1 via `@actions.action_name`
- Use `with param = value` for input binding (NOT `inputs:`)
- Use `set @variables.target = @outputs.source` for output capture (direct assignment ONLY — expressions like `(@outputs.x == "value")` are NOT supported)
- Use `with param = ...` for LLM slot-filling (extracts from conversation)
- Use `available when @variables.x == True` for conditional visibility
- `transition to @topic.X` CANNOT appear inside `instructions:` blocks — use transition action invocations instead

### 3.11 Instruction Syntax

Two instruction modes:

#### Literal Mode (`|`)
Static text that goes directly to the LLM. No expressions evaluated:
```
instructions: |
	Help the customer with their order.
	Be friendly and professional.
```

#### Procedural Mode (`->`)
Enables conditionals, variable injection, inline actions:
```
instructions: ->
	# Post-action check at TOP (deterministic)
	if @variables.case_id != "":
		| Your case {!@variables.case_id} has been created.
		transition to @topic.confirmation

	# Pre-LLM data loading
	run @actions.load_customer_data
		with customer_id = @variables.customer_id
		set @variables.risk_score = @outputs.risk_score

	# Dynamic instructions based on state
	| Customer risk score: {!@variables.risk_score}

	if @variables.risk_score >= 80:
		| HIGH RISK - Offer full cash refund to retain this customer.

	if @variables.risk_score < 80:
		| STANDARD - Offer $10 store credit as goodwill.
```

#### Variable Injection in Text
Use `{!@variables.name}` to inject variable values into literal text lines:
```
| Hello! Your order {!@variables.order_id} is currently {!@variables.order_status}.
```

### 3.12 Conditional Logic

Agent Script supports `if`, `else:`, and compound conditions:

```
if @variables.is_verified == True:
	| You are verified. Full access granted.

if @variables.is_verified == False:
	| Please verify your identity first.
```

With `else:`:
```
if @variables.churn_risk >= 80:
	| HIGH RISK - Offer retention package.
else:
	| STANDARD - Follow normal procedure.
```

Compound conditions (use instead of nested if):
```
if @variables.is_verified == True and @variables.is_premium == True:
	| Premium verified customer. VIP treatment.
```

#### Expression Operators

| Category | Supported | NOT Supported |
|----------|-----------|---------------|
| Comparison | `==`, `!=`, `<`, `<=`, `>`, `>=`, `is`, `is not` | `<>` |
| Logical | `and`, `or`, `not` | |
| Arithmetic | `+`, `-` | `*`, `/`, `%` |

### 3.13 Transitions and Delegation

| Syntax | Behavior | Returns? | Use When |
|--------|----------|----------|----------|
| `@utils.transition to @topic.X` | Permanent handoff | No | Checkout, escalation, final states |
| `@topic.X` (in reasoning.actions) | Delegation | Yes | Get expert advice, sub-tasks |
| `transition to @topic.X` (inline) | Deterministic jump | No | Post-action routing, gates |

Inline transition (inside `instructions: ->`):
```
if @variables.all_collected == True:
	transition to @topic.confirmation
```

Transition as action (inside `reasoning > actions:`):
```
go_to_orders: @utils.transition to @topic.order_support
	description: "Route to order support"
	available when @variables.has_order == True
```

Escalation to human:
```
escalate_now: @utils.escalate
	description: "Transfer to human agent"
```

### 3.14 The after_reasoning Pattern

`after_reasoning:` runs deterministically AFTER the LLM has produced its response for
each turn. The LLM output has already been sent to the user -- `after_reasoning` cannot
change what the LLM said. It runs on the NEXT cycle.

Place `after_reasoning:` at the topic level (same level as `reasoning:`):

```
topic collect_case_info:
	description: "Collect case details from the customer"

	reasoning:
		instructions: ->
			| Please provide the case subject and description.
			| I need both before I can create the case.

		actions:
			set_fields: @actions.capture_case_fields
				description: "Capture case subject and description"
				with subject = ...
				with desc_text = ...
				set @variables.case_subject = @outputs.subject
				set @variables.case_description = @outputs.desc_text

	after_reasoning: ->
		if @variables.case_subject != "" and @variables.case_description != "":
			run @actions.create_case
				with subject=@variables.case_subject
				with description=@variables.case_description
				set @variables.case_id = @outputs.case_id
		if @variables.case_id != "":
			transition to @topic.case_confirmation
```

Use `after_reasoning` when:
| Business Need | Pattern |
|---------------|---------|
| Create record after LLM collects all fields | `if allFieldsCollected: run @actions.create` |
| Route to next topic once condition met | `if @variables.X != "": transition to @topic.Y` |
| Audit-log every response | Unconditional `run @actions.log_event` (no `if`) |
| Escalate after too many turns | `if @variables.turn_count > 5: transition to @topic.escalate` |
| Chain actions then route | Multiple entries evaluated in sequence |

IMPORTANT: Content inside `after_reasoning:` goes directly under the block. There is
NO `instructions:` wrapper. Do NOT write `after_reasoning: instructions:`.

Valid content inside `after_reasoning:`:
- `if @variables.X == value:` blocks with executable statements inside
- `run @actions.X` with optional `with`/`set` clauses
- `transition to @topic.X`
- `set @variables.X = @outputs.Y` (ONLY after a `run @actions` statement)

NOT valid (causes SyntaxError):
- Standalone `set @variables.X = "value"` (not preceded by `run @actions`)
- `| literal text` lines
- `instructions:` wrapper

### 3.14b The before_reasoning Pattern

`before_reasoning:` runs deterministically BEFORE the reasoning loop starts on every request.
Use it for pre-loading data, permission checks, or deterministic routing:

```
topic customer_support:
	before_reasoning: ->
		if @variables.hotel_code != @variables.loaded_hotel_code:
			run @actions.get_account_info
				with account_id = @variables.account_id
				set @variables.hotel_code = @outputs.hotel_code
		run @actions.get_hotel_info
			with hotel_code = @variables.hotel_code
			set @variables.hotel_info = @outputs.hotel_info
```

Place `before_reasoning:` at the topic level (same level as `reasoning:` and `after_reasoning:`).

### 3.14c @utils.setVariables

Use `@utils.setVariables` as a reasoning action to let the LLM set mutable variables:

```
reasoning:
	actions:
		update_preferences: @utils.setVariables
			description: "Update customer preferences"
			with preferred_city = ...
			with max_price = ...
```

- Can only set mutable variables (not linked)
- Use `with var = ...` for LLM slot-filling (inherits description/type from variable definition)
- Use `with var = expression` for computed values
- Does NOT support post-action directives (`set`, `transition to`)

### 3.14d @system_variables.user_input

Built-in read-only variable providing the user's current message. No declaration needed:

```
reasoning:
	instructions: ->
		if @system_variables.user_input == "help":
			| Here are the available commands...
		else:
			| Process the request normally.
```

Use in: expressions, `available when`, template interpolation `{!@system_variables.user_input}`, action `with` clauses.
Cannot use in: `system.messages`, `set` assignments (read-only).

### 3.14e Dynamic Messages

System messages support variable interpolation with `{!@variables.name}`:

```
variables:
	customer_name: linked string
		source: @context.customerName
		description: "Customer name"

system:
	messages:
		welcome: "Hello {!@variables.customer_name}! How can I help?"
		error: "Sorry {!@variables.customer_name}, something went wrong."
```

Restrictions: Only linked (context) variables. No expressions. Simple `{!@variables.name}` references only.

### 3.15 Available When Guards

Control when actions are visible to the LLM:

```
actions:
	process_refund: @actions.issue_refund
		description: "Process a refund"
		available when @variables.is_verified == True
		available when @variables.has_order == True
		with order_id = @variables.order_id
```

Multiple `available when` clauses on the same action are valid (evaluated as AND).
However, for maximum portability across orgs, prefer a single compound condition:
```
available when @variables.is_verified == True and @variables.has_order == True
```

### 3.16 Slot-Filling with `...`

Use `...` (three dots) as an input value to let the LLM extract the value from
the conversation:

```
actions:
	search: @actions.search_inventory
		description: "Search for products"
		with query = ...
		with category = ...
```

The LLM reads the conversation history and fills in the values. Use this for
inputs that the user provides conversationally (not from variables).

### 3.17 Topic-Level Action Definitions with Targets

When a topic needs to define an action with a specific target (Flow, Apex, etc.),
place the full definition at the topic level under `actions:`, separate from
`reasoning:`:

```
topic home_search:
	label: "Home Search"
	description: "Search inventory for matching homes"

	actions:
		search_homes:
			description: "Search available homes"
			target: "flow://Search_Inventory"
			inputs:
				city: string
					description: "City to search"
				max_price: number
					description: "Maximum price"
			outputs:
				results_count: number
					description: "Number of homes found"
					is_displayable: True

	reasoning:
		instructions: ->
			| I can search for homes matching your criteria.

		actions:
			run_search: @actions.search_homes
				description: "Search for homes"
				with city = @variables.preferred_city
				with max_price = @variables.max_price
				set @variables.results_count = @outputs.results_count
```

### 3.18 Action I/O Metadata Properties

Action input and output definitions support these metadata properties:

| Property | Applies To | Purpose |
|----------|-----------|---------|
| (inline type) | input, output | Data type declared inline: `field_name: string`. Valid types: string, number, boolean, date, id, list, object, currency, datetime |
| `description` | input, output | Human-readable description |
| `is_displayable` | output | Whether to show the output to the user |
| `is_used_by_planner` | output | Whether the planner uses this for routing decisions |
| `is_user_input` | input | Whether the value comes from the end user |
| `label` | input, output | Human-readable label for the UI |
| `complex_data_type_name` | input, output | Lightning platform type for non-primitive types (see below) |

#### CRITICAL: Numeric Types in Action I/O

Bare `number` works for **variables** but **fails at publish** for action inputs/outputs. Action I/O numeric fields require `object` type + `complex_data_type_name`:

| WRONG (publish failure) | CORRECT |
|------------------------|---------|
| `minPrice: number` | `minPrice: object` with `complex_data_type_name` (see below) |
| `score: number` | `score: object` with `complex_data_type_name: "lightning__doubleType"` |

**CRITICAL: The correct `complex_data_type_name` for integers depends on the target type:**
- **Flow targets** (`flow://`): Use `lightning__numberType`
- **Apex targets** (`apex://`): Use `lightning__integerType`

Example (Flow target):
```
actions:
	search_homes:
		target: "flow://Search_Homes"
		inputs:
			city: string
			minPrice: object
				complex_data_type_name: "lightning__numberType"
		outputs:
			resultCount: object
				complex_data_type_name: "lightning__numberType"
```

Example (Apex target):
```
actions:
	book_reservation:
		target: "apex://ReservationHandler"
		inputs:
			party_size: object
				complex_data_type_name: "lightning__integerType"
```

> **Rule of thumb:** `number` → variables only. Action I/O → always `object` + `complex_data_type_name`. Flow targets → `lightning__numberType`. Apex targets → `lightning__integerType`.

See `references/complex-data-types.md` for the full mapping table.

---

## 4. SYNTAX CONSTRAINTS TABLE

These are validated errors. Violating these WILL cause compilation or deployment failure.

| Constraint | WRONG | CORRECT |
|------------|-------|---------|
| No `else if` keyword; no nested if | `else if x:` or nested `if` inside `else:` | `if x and y:` (compound) or sequential flat ifs |
| No `inputs:`/`outputs:` in Level 2 invocations | `inputs:` block inside `reasoning.actions:` | Use `with`/`set` in Level 2 invocations |
| No top-level `actions:` block | `actions:` at root level of the file | `actions:` only inside `topic` (Level 1) or `topic.reasoning` (Level 2) |
| Boolean values capitalized | `true` / `false` | `True` / `False` |
| Strings always double-quoted | `'hello'` or unquoted | `"hello"` |
| `developer_name` must match folder | Folder: `MyAgent`, config: `my_agent` | Both identical and case-sensitive |
| No defaults on linked variables | `id: linked string = ""` | `id: linked string` with `source:` |
| Linked vars: no object/list types | `data: linked object` | Use `linked string` and parse in Flow |
| `...` is slot-filling only | `my_var: mutable string = ...` | `my_var: mutable string = ""` |
| Avoid reserved field names as variables | `description: mutable string` | `desc_text: mutable string` |
| Always use `@actions.` prefix | `run set_user_name` | `run @actions.set_user_name` |
| Post-action `set`/`run` only on `@actions` | `@utils.X` with `set` | Only `@actions.X` supports post-action `set` |
| Every Level 2 `@actions.X` MUST have a matching Level 1 `X:` definition | `@actions.mark_resolved` with no Level 1 definition | Define `mark_resolved:` under `topic > actions:` first |
| Exactly one `start_agent` block | Multiple `start_agent:` entries | Single `start_agent topic_name:` (block syntax, NOT `start_agent: name`) |
| `start_agent` MUST have `description:` | `start_agent router:` with no `description:` | Add `description: "Route user requests"` — compiler requires it |
| `start_agent` MUST have `reasoning:` block | `start_agent router:` with no `reasoning:` | Add `reasoning: instructions:` and `reasoning: actions:` with transitions |
| `start_agent` instructions MUST say "router only" | `instructions: \| Determine intent and route.` | `instructions: \| You are a router only. Do NOT answer directly. Always use a transition action.` |
| `knowledge` is a reserved topic name | `topic knowledge:` | `topic knowledge_base:` or `topic faq:` |
| `fallback:` is NOT a valid message key | `messages: fallback: "..."` | Only `welcome:` and `error:` are valid under `messages:` |
| `datetime` not supported for mutable vars | `session_time: mutable datetime` | `session_time: mutable string` |
| Reasoning actions MUST use `@actions.` prefix | `validate: validate_vin` | `validate: @actions.validate_vin` |
| `required: True` invalid on reasoning invocations | Reasoning action with `required: True` | Only valid on Level 1 action definition inputs |
| No comment-only if bodies | `if @variables.x:` with only `# comment` | Add executable statement: `\| text`, `run`, `set`, or `transition` |
| `connection` not `connections` | `connections messaging:` | `connection messaging:` |
| No `@inputs` in `set` clauses | `set @variables.x = @inputs.y` | Use `@outputs.y` or `@utils.setVariables` |
| No `default:` sub-property on variables | `order_id: mutable string` + `default: ""` | `order_id: mutable string = ""` (inline default) |
| No nested `type:` in action I/O | `order_id:` + `type: string` | `order_id: string` (inline type) |
| Numeric action I/O needs complex type | `minPrice: number` in inputs/outputs | `minPrice: object` + `complex_data_type_name: "lightning__integerType"` |
| Linked var `source` uses `@` references | `source: "$Context.EndUserId"` | `source: @MessagingSession.MessagingEndUserId` |
| No `connection:` without `messaging` | `connection:` + `type: "OmniChannel"` | `connection messaging:` with `routing_type:` inside |
| No nested description under `...` | `with x = ...` + indented `description:` | `with x = ...` (description inherited from Level 1 definition) |
| Use `developer_name` not `agent_name` | `agent_name: "MyAgent"` | `developer_name: "MyAgent"` (do not use both — causes "only one can be provided" error) |
| `target:` must be quoted | `target: apex://Handler` | `target: "apex://Handler"` |
| `system:` needs `instructions:` sub-block | Raw text under `system:` | `system:` → `instructions: \|` → text |
| `messages:` inside `system:` block | Top-level `messages:` block | `system:` → `messages:` → `welcome:` / `error:` |
| Invalid locale codes | `ja_JP`, `es_US` | `ja`, `es` or `es_MX` |
| `after_reasoning` no pipe literals | `\| text` in `after_reasoning:` | Only `set`, `if`/`else`, `transition to` |

### Syntax Pitfalls (Compiler Errors)

These patterns look reasonable but cause compiler errors. Use the correct forms:

```
❌ WRONG — `default:` as sub-property:
	order_id: mutable string
		default: ""

✅ CORRECT — inline default:
	order_id: mutable string = ""

❌ WRONG — nested `type:` in action I/O:
	inputs:
		order_id:
			type: string

✅ CORRECT — inline type:
	inputs:
		order_id: string
```

### Reserved Field Names

These names CANNOT be used as variable names or action I/O field names:
```
RESERVED:  description, label, is_required, is_displayable, is_used_by_planner

USE INSTEAD:
  description  -> desc_text, description_field
  label        -> label_text, display_label
```

NOTE: These keywords ARE valid as metadata properties on action definitions (e.g.,
`is_required: True` on an input). They just cannot be used as the NAME of a variable
or I/O field.

---

## 5. NAMING CONVENTIONS

| Element | Convention | Example |
|---------|-----------|---------|
| Agent name | PascalCase or underscore-separated | `AcmeAgent`, `Acme_Agent` |
| `developer_name` in config | Must match folder name exactly | `AcmeAgent` |
| Topic names | snake_case | `order_support`, `identity_verification` |
| Variable names | camelCase or snake_case (consistent) | `orderId`, `order_id` |
| Action definition names (Level 1) | snake_case | `get_order_status`, `create_case` |
| Action invocation names (Level 2) | snake_case | `lookup_order`, `create_new_case` |
| Labels | Human-readable with spaces | `"Order Support"`, `"Create Case"` |

Naming rules:
- Only letters, numbers, underscores
- Must begin with a letter
- No spaces, no consecutive underscores, cannot end with underscore
- Maximum 80 characters

---

## 6. 100-POINT SCORING RUBRIC

Score every generated agent against this rubric before presenting to the user.

| Category | Points | Key Criteria |
|----------|--------|--------------|
| Structure & Syntax | 15 | All required blocks present (`config`, `system`, `start_agent`, at least one `topic`). Proper nesting. Consistent tab indentation (see Section 3.1b). No mixed tabs/spaces. Valid field names. All string values double-quoted. |
| Safety & Responsible AI | 15 | Evaluated via `adlc-safety` skill (7 categories): AI disclosure present, no impersonation/deception/manipulation, responsible data handling, no harmful content (including euphemisms), no discrimination (direct or proxy), clear scope boundaries, escalation paths for sensitive topics. Deduct 15 for any BLOCK finding, 5 per WARN finding. |
| Deterministic Logic | 20 | `after_reasoning` patterns for post-action routing. FSM transitions with no dead-end topics. `available when` guards for security-sensitive actions. Post-action checks at TOP of `instructions: ->`. |
| Instruction Resolution | 20 | Clear, actionable instructions. Procedural mode (`->`) where conditionals are needed. Literal mode (`\|`) where static text suffices. Variable injection where dynamic. Conditional instructions based on state. |
| FSM Architecture | 10 | Hub-and-spoke or verification gate pattern. Every topic reachable. Every topic has an exit (transition or escalation). No orphan topics. Start topic routes correctly. |
| Action Configuration | 10 | Proper Level 1 definitions with targets and I/O schemas. Correct Level 2 invocations with `with`/`set`. Slot-filling (`...`) for conversational inputs. Output capture into variables. Numeric I/O uses `object` + `complex_data_type_name` (never bare `number`). |
| Deployment Readiness | 10 | Valid `default_agent_user`. `developer_name` matches folder. `bundle-meta.xml` present with `<bundleType>AGENT</bundleType>`. Linked variables for service agents (`EndUserId`, `RoutableId`, `ContactId`). |

### Score Interpretation

| Score | Meaning | Action |
|-------|---------|--------|
| 90-100 | Production-ready | Deploy with confidence |
| 75-89 | Good with minor issues | Fix noted items, then deploy |
| 60-74 | Needs work | Address structural issues before deploy |
| Below 60 | BLOCK | Major rework required |

---

## 7. DEPLOYMENT GOTCHAS

Common mistakes that cause deployment failures:

| WRONG | CORRECT |
|-------|---------|
| `AgentName.aiAuthoringBundle-meta.xml` | `AgentName.bundle-meta.xml` |
| bundle-meta.xml with `<developerName>`, `<masterLabel>`, or `<target>` | Minimal: only `<bundleType>AGENT</bundleType>` |
| `sf project deploy start` for agents | `sf agent publish authoring-bundle --api-name X -o Org` |
| `sf agent validate --source-dir` | `sf agent validate authoring-bundle --api-name X -o Org` |
| Query Einstein Agent User from wrong org | Query the TARGET org specifically with `-o` flag |
| Publish and assume active | Publish does NOT activate. Run `sf agent activate` separately |
| `start_agent` and `topic` share the same name | Use different names — both create `GenAiPluginDefinition` records that collide on publish |

### Bundle Directory Structure

```
force-app/main/default/aiAuthoringBundles/MyAgent/
  MyAgent.agent              # Agent Script file
  MyAgent.bundle-meta.xml    # NOT .aiAuthoringBundle-meta.xml
```

### Einstein Agent User Format

The username format varies by org type:
- Production: `username@orgid.ext`
- Dev/Scratch: `username.suffix@orgfarm.salesforce.com`

ALWAYS query the target org to get the correct value. Never guess.

### Deployment Lifecycle

```
Validate -> Publish -> Activate -> (Deactivate -> Re-publish -> Re-activate)
```

Commands:
```bash
# Validate
sf agent validate authoring-bundle --api-name MyAgent -o TargetOrg --json

# Publish
sf agent publish authoring-bundle --api-name MyAgent -o TargetOrg --json

# Activate (no --json support)
sf agent activate --api-name MyAgent -o TargetOrg

# Open in Agentforce Studio
sf org open authoring-bundle -o TargetOrg
```

---

## 8. ARCHITECTURE PATTERNS

### Hub-and-Spoke (Most Common)

A central `topic_selector` routes to specialized spoke topics. Each spoke has a
"back to hub" transition. Use when users may have multiple distinct intents.

```
start_agent hub_router:
	description: "Route user requests to the appropriate topic"

topic topic_selector:
	description: "Route based on user intent"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions directly.
			Always use a transition action to route immediately.
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Order questions"
			to_returns: @utils.transition to @topic.return_support
				description: "Return or refund requests"
			to_general: @utils.transition to @topic.general_support
				description: "General questions"

topic order_support:
	description: "Handle order inquiries"
	reasoning:
		instructions: ->
			| Help the customer with their order.
		actions:
			back: @utils.transition to @topic.topic_selector
				description: "Return to main menu"
```

> Note: `start_agent hub_router:` uses a different name from `topic topic_selector:` to avoid `GenAiPluginDefinition` name collision on publish.

> **Dead hub warning:** If `topic_selector` only contains transition actions and no real business logic, consider consolidating its routing into `start_agent > reasoning > actions:` directly. An intermediate routing-only topic adds an extra LLM hop (~3-5s latency) with no benefit. Use a separate `topic_selector` only when it performs real work (e.g., collecting disambiguation info, displaying a menu, or running a pre-routing action).

### Verification Gate

Users must pass through identity verification before accessing protected topics.
Use when handling sensitive data, payments, or PII.

```
start_agent gate_router:
	description: "Route through identity verification"

topic welcome:
	description: "Entry - routes through verification"
	reasoning:
		instructions: |
			Welcome the customer and begin verification.
		actions:
			verify: @utils.transition to @topic.identity_verification
				description: "Begin verification"

topic identity_verification:
	description: "Verify customer identity"
	reasoning:
		instructions: ->
			if @variables.failed_attempts >= 3:
				| Too many failed attempts. Transferring to human agent.
				transition to @topic.escalation

			if @variables.is_verified == True:
				| Identity verified! How can I help?

			if @variables.is_verified == False:
				| Please verify your identity.

		actions:
			verify_email: @actions.verify_identity
				description: "Verify customer email"
				set @variables.is_verified = @outputs.verified

			to_account: @utils.transition to @topic.account_mgmt
				description: "Account management"
				available when @variables.is_verified == True

			escalate_now: @utils.escalate
				description: "Transfer to human"
```

### Post-Action Loop

The topic re-resolves after an action completes. Place post-action checks at the
TOP of `instructions: ->` so they trigger on the loop:

```
reasoning:
	instructions: ->
		# POST-ACTION CHECK (at TOP - triggers on re-resolution)
		if @variables.refund_status == "Approved":
			run @actions.create_crm_case
				with customer_id = @variables.customer_id
			transition to @topic.confirmation

		# PRE-LLM: Load data
		run @actions.load_risk_score
			with customer_id = @variables.customer_id
			set @variables.risk_score = @outputs.score

		# DYNAMIC INSTRUCTIONS
		| Risk score: {!@variables.risk_score}
		if @variables.risk_score >= 80:
			| HIGH RISK - Offer retention package.
		else:
			| STANDARD - Follow normal process.
```

---

## 9. COMPLETE EXAMPLE: Minimal Service Agent

This is the absolute minimum for a deployable service agent:

```
system:
	instructions: "You are a helpful customer service agent."
	messages:
		welcome: "Hello! How can I help you today?"
		error: "Something went wrong. Please try again."

config:
	developer_name: "MinimalAgent"
	agent_label: "Minimal Agent"
	description: "A minimal service agent"
	default_agent_user: "agent@00dxx000001234.ext"

variables:
	EndUserId: linked string
		source: @MessagingSession.MessagingEndUserId
		description: "Messaging End User ID"
		visibility: "External"
	RoutableId: linked string
		source: @MessagingSession.Id
		description: "Messaging Session ID"
		visibility: "External"
	ContactId: linked string
		source: @MessagingEndUser.ContactId
		description: "Contact ID"
		visibility: "External"

language:
	default_locale: "en_US"
	additional_locales: ""
	all_additional_locales: False

start_agent linear_router:
	description: "Begin the onboarding flow"

topic greeting:
	label: "Greeting"
	description: "Greet users and provide help"
	reasoning:
		instructions: ->
			| Welcome the user warmly.
			| Ask how you can help them today.
```

Companion `bundle-meta.xml` (MUST be this exact content — no extra fields):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<AiAuthoringBundle xmlns="http://soap.sforce.com/2006/04/metadata">
  <bundleType>AGENT</bundleType>
</AiAuthoringBundle>
```

---

## 10. COMPLETE EXAMPLE: Multi-Topic Agent with Actions

```
system:
	instructions: |
		You are a customer service agent for TechCorp.
		Be professional, concise, and solution-oriented.
		Always verify the customer before sensitive operations.
	messages:
		welcome: "Welcome to TechCorp Support! How can I assist you?"
		error: "I apologize for the issue. Please try again."

config:
	developer_name: "TechCorpAgent"
	agent_label: "TechCorp Support Agent"
	description: "Handles order inquiries, returns, and general support"
	default_agent_user: "einstein@00dxx000001234.ext"

variables:
	EndUserId: linked string
		source: @MessagingSession.MessagingEndUserId
		description: "Messaging End User ID"
		visibility: "External"
	RoutableId: linked string
		source: @MessagingSession.Id
		description: "Messaging Session ID"
		visibility: "External"
	ContactId: linked string
		source: @MessagingEndUser.ContactId
		description: "Contact ID"
		visibility: "External"
	order_id: mutable string = ""
		description: "Current order being discussed"
	order_status: mutable string = ""
		description: "Status of the current order"
	is_verified: mutable boolean = False
		description: "Customer verification status"
	case_id: mutable string = ""
		description: "Created case ID"

language:
	default_locale: "en_US"
	additional_locales: ""
	all_additional_locales: False

start_agent multi_router:
	description: "Route customers to the right support topic"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions or provide help directly.
			Always use a transition action to route to the correct topic immediately.
			- Order status or tracking → use to_orders
			- Returns or refunds → use to_returns
			- General questions → use to_general
			Never attempt to help the customer yourself. Always route.
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Check order status or tracking"
			to_returns: @utils.transition to @topic.return_support
				description: "Process a return or refund"
			to_general: @utils.transition to @topic.general_support
				description: "General questions and support"

topic main_menu:
	label: "Main Menu"
	description: "Re-route returning customers to the right topic"
	reasoning:
		instructions: |
			The customer wants to do something else.
			Ask what they need and route them accordingly.
			- Order status or tracking → use to_orders
			- Returns or refunds → use to_returns
			- General questions → use to_general
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Check order status or tracking"
			to_returns: @utils.transition to @topic.return_support
				description: "Process a return or refund"
			to_general: @utils.transition to @topic.general_support
				description: "General questions and support"

topic order_support:
	label: "Order Support"
	description: "Handle order status and tracking inquiries"

	actions:
		get_order:
			description: "Look up order by ID"
			target: "flow://Get_Order_Status"
			inputs:
				order_id: string
					description: "Order ID"
			outputs:
				status: string
					description: "Order status"
					is_displayable: True
				tracking_url: string
					description: "Tracking URL"
					is_displayable: True

	reasoning:
		instructions: ->
			if @variables.order_status != "":
				| Order {!@variables.order_id} status: {!@variables.order_status}

			| What is your order number?

		actions:
			lookup: @actions.get_order
				description: "Look up order"
				with order_id = ...
				set @variables.order_id = @outputs.order_id
				set @variables.order_status = @outputs.status

			back: @utils.transition to @topic.main_menu
				description: "Return to main menu"

topic return_support:
	label: "Return Support"
	description: "Handle returns and refund requests"

	actions:
		initiate_return:
			description: "Start a return process"
			target: "flow://Initiate_Return"
			inputs:
				order_id: string
					description: "Order ID for the return"
				reason: string
					description: "Reason for return"
			outputs:
				return_id: string
					description: "Return authorization ID"
					is_displayable: True

	reasoning:
		instructions: ->
			| I can help with your return request.
			| Please provide your order number and the reason for the return.

		actions:
			start_return: @actions.initiate_return
				description: "Start a return"
				with order_id = ...
				with reason = ...
				set @variables.case_id = @outputs.return_id

			back: @utils.transition to @topic.main_menu
				description: "Return to main menu"

	after_reasoning:
		if @variables.case_id != "":
			transition to @topic.confirmation

topic general_support:
	label: "General Support"
	description: "Handle general support questions"
	reasoning:
		instructions: |
			Help the customer with general questions.
			If the question is about orders or returns, route appropriately.
		actions:
			escalate_now: @utils.escalate
				description: "Transfer to human agent"
			back: @utils.transition to @topic.main_menu
				description: "Return to main menu"

topic confirmation:
	label: "Confirmation"
	description: "Confirm the completed action"
	reasoning:
		instructions: ->
			| Your request has been processed. Reference: {!@variables.case_id}
			| Is there anything else I can help with?
		actions:
			new_request: @utils.transition to @topic.main_menu
				description: "Start a new request"
			end_chat: @actions.end_conversation
				description: "End the conversation"
```

---

## 11. PRODUCTION GOTCHAS

### Credit Consumption

- Framework operations (`@utils.*`, `if`/`else`, `set`, lifecycle hooks) are FREE
- Flow/Apex/API actions cost 20 credits each per invocation
- Minimize action calls by caching results in variables

### Lifecycle Hooks

- `before_reasoning:` and `after_reasoning:` content goes DIRECTLY under the block
- There is NO `instructions:` wrapper inside lifecycle hooks
- Use `filter_from_agent: True` + `is_used_by_planner: True` on outputs for
  zero-hallucination routing

### Latch Variable Pattern

Use a boolean "latch" to prevent re-execution of one-time actions:
```
if @variables.data_loaded == False:
	run @actions.load_data
		with id = @variables.customer_id
		set @variables.customer_name = @outputs.name
	set @variables.data_loaded = True
```

### Token Limits

Large agents with many topics and actions can exceed token limits. Keep instructions
concise. Use `filter_from_agent: True` on actions that should not appear in the
planner prompt.

---

## 12. REFERENCE DOC MAP

| Need | Reference |
|------|-----------|
| Credit consumption, lifecycle hooks, supervision, limits | `references/production-gotchas.md` (planned) |
| Which properties work in which contexts | `references/feature-validity.md` (planned) |
| Agent Script to Lightning type mapping | `references/complex-data-types.md` |
| Preview smoke test loop (Phase 3.5 rapid feedback) | `references/preview-test-loop.md` |
| Action definitions, targets, I/O binding, troubleshooting | `references/actions-reference.md` (planned) |
| How instructions resolve at runtime (3-phase model) | `references/instruction-resolution.md` (planned) |
| Reading traces, diagnosing issues, jq recipes | `references/debugging-guide.md` |
| Tracked platform issues and workarounds | `references/known-issues.md` (planned) |

---

## 13. TEMPLATE ASSETS

> **Note:** The template files listed below are planned but not yet available.
> Use the complete examples in Sections 9 and 10 as starting points for new agents.

| Template | Description | File |
|----------|-------------|------|
| Hello World | Minimal single-topic agent | `assets/hello-world.agent` (planned) |
| Multi-Topic | Two topics with routing | `assets/multi-topic.agent` (planned) |
| Verification Gate | Identity verification before protected topics | `assets/verification-gate.agent` (planned) |
| Hub-and-Spoke | Central router with specialized spokes | `assets/hub-and-spoke.agent` (planned) |
| Order Service | Complex real-world agent with flows | `assets/order-service.agent` (planned) |
| Bundle Metadata | Companion XML template | `assets/metadata/bundle-meta.xml` (planned) |

When generating a new agent, use the inline examples in Sections 9 (Minimal Service Agent)
and 10 (Multi-Topic Agent with Actions) as starting points, then customize.

---

## 14. REVIEW MODE

When the user provides a path to an existing `.agent` file (e.g., `review path/to/file.agent`):

1. Read the file with the Read tool
2. Score it against the 100-point rubric (Section 6)
3. List every issue found, grouped by category
4. Provide corrected code snippets for each issue
5. Offer to apply all fixes via Edit tool

Common review findings:
- Missing linked variables for service agents
- `developer_name` not matching folder name
- Missing `language:` block
- Actions missing I/O schemas (Level 1 definitions)
- Dead-end topics with no exit transition
- `instructions: |` used where `instructions: ->` is needed (conditionals present)
- Boolean values not capitalized (`true` instead of `True`)
- Missing `after_reasoning` for post-action routing
- **Safety: System instructions don't identify agent as AI**
- **Safety: No defined boundaries (what agent will NOT do)**
- **Safety: Missing escalation path for edge cases**
- **Safety: Sensitive actions lack `available when` guards**

---

## 15. FEEDBACK

After completing agent authoring (or if the user ran into issues), offer to collect feedback:

```
Your agent file is ready! If you have a moment, I can help you share quick feedback
on how the authoring process went — what worked, what was confusing, or ideas for improvement.
Just say /adlc-feedback and I'll draft it for you.
```

Only mention this once, at the natural end of the workflow. Do not repeat or push if the user ignores it.
