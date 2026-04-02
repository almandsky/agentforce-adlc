# Agent Script Syntax Reference

> Extracted from SKILL.md Sections 3 + 4. This file is loaded on demand when detailed syntax rules are needed.

## Block Structure (Required Order)

```
config:           # 1. REQUIRED: Agent metadata
variables:        # 2. Optional: Mutable state and linked context
system:           # 3. REQUIRED: Global instructions and messages
connection messaging:  # 4. Optional: Escalation routing (service agents)
knowledge:        # 5. Optional: Knowledge base config
language:         # 6. Optional: Locale settings
start_agent topic_selector:  # 7. REQUIRED: Entry point (always name it topic_selector)
topic:            # 8. REQUIRED: Conversation topics (one or more)
```

## Indentation

Agent Script is whitespace-delimited. **Use tabs for all indentation.** The server rejects space-based indentation (including 3-space).

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

**CRITICAL:** Before generating, read any existing `.agent` file in the project to match its indentation style exactly.

## Config Block

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

**WARNING: Do NOT include `agent_type` in the `.agent` file.** The server crashes with a null pointer. Set the agent type via Setup UI after publish.

## Variables Block

### Mutable Variables (read-write state)
```
variables:
	order_id: mutable string = ""
		description: "Current order being discussed"
	is_verified: mutable boolean = False
		description: "Whether customer has been verified"
	attempt_count: mutable number = 0
		description: "Number of verification attempts"
```

### Linked Variables (read-only context)
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

### Variable Type Reference

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
- Use `timestamp` instead of `datetime` for mutable date+time variables
- Use `number` instead of `integer`/`long` for mutable numeric variables
- Service agents auto-add `EndUserId`, `RoutableId`, `ContactId` as linked variables
- The `...` token is for slot-filling only (in `with param=...`), never as a default

## System Block

```
system:
	instructions: |
		You are a customer service agent.
		Be professional, concise, and helpful.
	messages:
		welcome: "Hello! How can I help you today?"
		error: "Something went wrong. Please try again."
```

Topics can override the agent-level `system:` with their own topic-level `system:` block.

## Connection Block (Service Agents Only)

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

NOTE: Use `connection messaging:` (singular). NOT `connections:`. When `outbound_route_type` is present, ALL three route properties are required. Valid channel types: `messaging`, `voice`, `web`.

## Language Block

```
language:
	default_locale: "en_US"
	additional_locales: ""
	all_additional_locales: False
```

Valid locale codes: `ar, bg, ca, cs, da, de, el, en_AU, en_GB, en_US, es, es_MX, et, fi, fr, fr_CA, he, hi, hr, hu, id, in, it, iw, ja, ko, ms, nl_NL, no, pl, pt_BR, pt_PT, ro, sv, th, tl, tr, vi, zh_CN, zh_TW`. Common mistakes: `ja_JP` -> use `ja`, `es_US` -> use `es` or `es_MX`.

## Knowledge Block

```
knowledge:
	citations_enabled: True
```

## Start Agent

Exactly one `start_agent` entry point per agent. **Always name it `topic_selector`.**

**CRITICAL: `start_agent` MUST include `description:`, `reasoning: instructions:`, and `reasoning: actions:`.**

```
start_agent topic_selector:
	description: "Route user requests to the appropriate topic"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions or provide help directly.
			Always use a transition action to route to the correct topic immediately.
			- Order questions -> use to_orders
			- Return requests -> use to_returns
			Never attempt to help the user yourself. Always route.
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Route to order support"
			to_returns: @utils.transition to @topic.return_support
				description: "Route to returns"
```

Key rules:
- Router-only instructions are CRITICAL -- without them the LLM answers directly instead of routing
- The `start_agent` name MUST differ from all `topic` names (both create `GenAiPluginDefinition` records)
- Do NOT create a separate routing/menu topic -- `start_agent` IS the central router

## Topic Block

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

	reasoning:
		instructions: ->
			| Help the customer check their order status.

		actions:
			# Level 2: Action INVOCATIONS (with/set bindings)
			lookup_order: @actions.get_order_status
				description: "Look up order details"
				with order_id = @variables.order_id
				set @variables.order_status = @outputs.status

			back_to_menu: @utils.transition to @topic.topic_selector
				description: "Route to a different topic"
```

## Two-Level Action System (CRITICAL)

### Level 1: Action Definitions

Located inside `topic > actions:`. Defines WHAT the action is:

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

Target protocols:
- `flow://Flow_Api_Name` -- Autolaunched Flow
- `apex://ClassName` -- Apex @InvocableMethod
- `prompt://TemplateName` (or `generatePromptResponse://`) -- Prompt Template
- `externalService://ServiceName.operationName` -- External Service
- `retriever://RetrieverName` -- Knowledge retrieval
- `standardInvocableAction://ActionName` -- Built-in Salesforce action
- `quickAction://ActionName` -- Quick Action
- `api://ApiName` -- REST API
- `apexRest://EndpointName` -- Custom Apex REST endpoint
- `mcpTool://ToolName` -- MCP Tool

I/O schemas (`inputs:` + `outputs:`) are REQUIRED for publish.

### Level 2: Action Invocations

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

Key rules:
- Reference Level 1 via `@actions.action_name`
- Use `with param = value` for input binding (NOT `inputs:`)
- Use `set @variables.target = @outputs.source` for output capture (direct assignment ONLY)
- Use `with param = ...` for LLM slot-filling
- Use `available when @variables.x == True` for conditional visibility

## Instruction Syntax

### Literal Mode (`|`)
```
instructions: |
	Help the customer with their order.
	Be friendly and professional.
```

### Procedural Mode (`->`)
```
instructions: ->
	if @variables.case_id != "":
		| Your case {!@variables.case_id} has been created.
		transition to @topic.confirmation

	run @actions.load_customer_data
		with customer_id = @variables.customer_id
		set @variables.risk_score = @outputs.risk_score

	| Customer risk score: {!@variables.risk_score}

	if @variables.risk_score >= 80:
		| HIGH RISK - Offer full cash refund.
	if @variables.risk_score < 80:
		| STANDARD - Offer $10 store credit.
```

### Variable Injection
Use `{!@variables.name}` to inject variable values into literal text lines.

## Conditional Logic

```
if @variables.is_verified == True:
	| You are verified. Full access granted.
else:
	| Please verify your identity first.
```

Compound conditions (use instead of nested if):
```
if @variables.is_verified == True and @variables.is_premium == True:
	| Premium verified customer. VIP treatment.
```

### Expression Operators

| Category | Supported | NOT Supported |
|----------|-----------|---------------|
| Comparison | `==`, `!=`, `<`, `<=`, `>`, `>=`, `is`, `is not` | `<>` |
| Logical | `and`, `or`, `not` | |
| Arithmetic | `+`, `-` | `*`, `/`, `%` |

## Transitions and Delegation

| Syntax | Behavior | Returns? | Use When |
|--------|----------|----------|----------|
| `@utils.transition to @topic.X` | Permanent handoff | No | Checkout, escalation |
| `@topic.X` (in reasoning.actions) | Delegation | Yes | Sub-tasks |
| `transition to @topic.X` (inline) | Deterministic jump | No | Post-action routing |

Escalation to human:
```
escalate_now: @utils.escalate
	description: "Transfer to human agent"
```

## The after_reasoning Pattern

Runs deterministically AFTER the LLM response. Place at topic level:

```
after_reasoning: ->
	if @variables.case_subject != "" and @variables.case_description != "":
		run @actions.create_case
			with subject=@variables.case_subject
			with description=@variables.case_description
			set @variables.case_id = @outputs.case_id
	if @variables.case_id != "":
		transition to @topic.case_confirmation
```

IMPORTANT: No `instructions:` wrapper. Valid content: `if`, `run @actions`, `transition to`, `set` (only after `run`). NOT valid: `| literal text`, standalone `set`.

## The before_reasoning Pattern

Runs deterministically BEFORE reasoning on every request:

```
before_reasoning: ->
	if @variables.hotel_code != @variables.loaded_hotel_code:
		run @actions.get_account_info
			with account_id = @variables.account_id
			set @variables.hotel_code = @outputs.hotel_code
```

## @utils.setVariables

Let the LLM set mutable variables:

```
reasoning:
	actions:
		update_preferences: @utils.setVariables
			description: "Update customer preferences"
			with preferred_city = ...
			with max_price = ...
```

Does NOT support `set` or `transition to`.

## @system_variables.user_input

Built-in read-only variable for the user's current message. No declaration needed.

## Dynamic Messages

```
system:
	messages:
		welcome: "Hello {!@variables.customer_name}! How can I help?"
```

Restrictions: Only linked variables. No expressions.

## Available When Guards

```
process_refund: @actions.issue_refund
	description: "Process a refund"
	available when @variables.is_verified == True and @variables.has_order == True
```

## Slot-Filling with `...`

```
search: @actions.search_inventory
	description: "Search for products"
	with query = ...
	with category = ...
```

## Numeric Types in Action I/O (CRITICAL)

Bare `number` works for variables but fails at publish for action I/O. Use `object` + `complex_data_type_name`:

- **Flow targets** (`flow://`): `complex_data_type_name: "lightning__numberType"`
- **Apex targets** (`apex://`): `complex_data_type_name: "lightning__integerType"`

See `references/complex-data-types.md` for the full mapping table.

---

## Syntax Constraints Table

| Constraint | WRONG | CORRECT |
|------------|-------|---------|
| No `else if`; no nested if | `else if x:` | `if x and y:` (compound) or sequential flat ifs |
| No `inputs:`/`outputs:` in Level 2 | `inputs:` in `reasoning.actions:` | Use `with`/`set` |
| No top-level `actions:` block | `actions:` at root level | Inside `topic` or `topic.reasoning` only |
| Booleans capitalized | `true`/`false` | `True`/`False` |
| Strings double-quoted | `'hello'` | `"hello"` |
| `developer_name` matches folder | Folder: `MyAgent`, config: `my_agent` | Both identical, case-sensitive |
| No defaults on linked variables | `id: linked string = ""` | `id: linked string` with `source:` |
| `...` is slot-filling only | `my_var: mutable string = ...` | `my_var: mutable string = ""` |
| Avoid reserved field names | `description: mutable string` | `desc_text: mutable string` |
| Always use `@actions.` prefix | `run set_user_name` | `run @actions.set_user_name` |
| Post-action `set` only on `@actions` | `@utils.X` with `set` | Only `@actions.X` supports `set` |
| Every Level 2 needs matching Level 1 | `@actions.mark_resolved` with no definition | Define under `topic > actions:` first |
| Exactly one `start_agent` | Multiple `start_agent:` entries | Single `start_agent topic_name:` |
| `start_agent` MUST have `description:` | No `description:` | Add `description: "Route user requests"` |
| `start_agent` MUST have `reasoning:` | No `reasoning:` block | Add `reasoning: instructions:` + `actions:` |
| `start_agent` says "router only" | Vague routing instructions | "You are a router only. Do NOT answer directly." |
| `knowledge` is reserved topic name | `topic knowledge:` | `topic knowledge_base:` or `topic faq:` |
| `fallback:` not valid message key | `messages: fallback:` | Only `welcome:` and `error:` |
| `datetime` not for mutable vars | `session_time: mutable datetime` | `session_time: mutable string` |
| No comment-only if bodies | `if @variables.x:` with only `# comment` | Add executable statement |
| `connection` not `connections` | `connections messaging:` | `connection messaging:` |
| No `@inputs` in `set` clauses | `set @variables.x = @inputs.y` | Use `@outputs.y` |
| No `agent_type` in config | `agent_type: "..."` | Omit entirely |
| Tabs only for indentation | Spaces | Tabs at every level |
| No `default:` sub-property | `default: ""` | Inline: `= ""` |
| No nested `type:` in I/O | `type: string` | Inline: `order_id: string` |
| Numeric I/O needs complex type | `minPrice: number` | `minPrice: object` + `complex_data_type_name` |
| Linked var `source` uses `@` | `source: "$Context.EndUserId"` | `source: @MessagingSession.MessagingEndUserId` |
| No `connection:` without channel | `connection:` | `connection messaging:` |
| No nested description under `...` | `with x = ...` + `description:` | Description inherited from Level 1 |
| Use `developer_name` not `agent_name` | `agent_name: "MyAgent"` | `developer_name: "MyAgent"` |
| `target:` must be quoted | `target: apex://Handler` | `target: "apex://Handler"` |
| Apex target: class name only | `target: "apex://Svc.method"` | `target: "apex://SvcMethod"` |
| `system:` needs `instructions:` | Raw text under `system:` | `system: instructions: \|` |
| `messages:` inside `system:` | Top-level `messages:` | `system: messages:` |
| Invalid locale codes | `ja_JP`, `es_US` | `ja`, `es` or `es_MX` |
| No pipe literals in `after_reasoning` | `\| text` | Only `set`, `if`, `transition to` |
| Procedural `->` can't have bare `\|` after if | Mixed content | Use literal `\|` mode or wrap in if/else |

### Syntax Pitfalls (Compiler Errors)

```
WRONG -- `default:` as sub-property:
	order_id: mutable string
		default: ""

CORRECT -- inline default:
	order_id: mutable string = ""

WRONG -- nested `type:` in action I/O:
	inputs:
		order_id:
			type: string

CORRECT -- inline type:
	inputs:
		order_id: string
```

### Reserved Field Names

```
RESERVED:  description, label, is_required, is_displayable, is_used_by_planner, language, escalate

USE INSTEAD:
  description  -> desc_text, description_field
  label        -> label_text, display_label
  language     -> response_language, lang_preference
  escalate     -> escalate_to_agent, transfer_to_agent
```

These keywords ARE valid as metadata properties (e.g., `is_required: True` on an input). They just cannot be used as the NAME of a variable, I/O field, or action definition.
