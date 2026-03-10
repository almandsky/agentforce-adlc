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
1. Gathers requirements through targeted questions
2. Queries the target org for the Einstein Agent User
3. Generates a complete `.agent` file using Agent Script DSL
4. Creates the companion `bundle-meta.xml`
5. Validates the output via CLI
6. Presents a 100-point quality score

### When to Use This Skill

- Building a new Agentforce agent from scratch
- Rewriting an existing agent from requirements
- Reviewing an `.agent` file for quality and correctness

### When NOT to Use This Skill

- Testing an existing agent (use adlc-run)
- Deploying an agent to an org (use adlc-deploy)
- Discovering org metadata for action targets (use adlc-discover)

---

## 2. WORKFLOW PHASES

### Phase 1: Requirements

Ask the user for the following. Do not proceed until each is answered or explicitly skipped:

| Question | Why It Matters |
|----------|---------------|
| Target org alias | Needed to query Einstein Agent User |
| Agent name (PascalCase) | Becomes `developer_name`, folder name, and bundle name |
| Agent type: Service or Employee | Determines linked variables and connection block |
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

If validation fails, read the error output, fix the `.agent` file, and re-validate.

### Phase 5: Review

Present the generated file with a 100-point score breakdown (see Section 6).

---

## 3. AGENT SCRIPT SYNTAX REFERENCE

This section contains the complete Agent Script DSL syntax. It is self-contained:
you should not need any external reference document for common agent authoring tasks.

### 3.1 Block Structure (Required Order)

```
config:           # 1. REQUIRED: Agent metadata
variables:        # 2. Optional: Mutable state and linked context
system:           # 3. REQUIRED: Global instructions and messages
connection:       # 4. Optional: Escalation routing (service agents)
knowledge:        # 5. Optional: Knowledge base config
language:         # 6. Optional: Locale settings
start_agent:      # 7. REQUIRED: Entry point (exactly one)
topic:            # 8. REQUIRED: Conversation topics (one or more)
```

### 3.2 Config Block

The `config:` block defines agent metadata. Field names are exact -- do not substitute.

```
config:
   developer_name: "MyAgent"
   agent_label: "My Agent"
   description: "What this agent does"
   default_agent_user: "einsteinagent@00dxx000001234.ext"
   agent_type: "AgentforceServiceAgent"
```

| Field | Required | Notes |
|-------|----------|-------|
| `developer_name` | Yes | MUST match the folder name (case-sensitive) |
| `agent_label` | Yes | Human-readable display name |
| `description` | Yes | Agent purpose (used for routing) |
| `default_agent_user` | Yes | Must be a valid Einstein Agent User in the target org |
| `agent_type` | Yes | `AgentforceServiceAgent` or `AgentforceEmployeeAgent` |

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

| Type | Mutable | Linked | Default Format |
|------|---------|--------|---------------|
| `string` | Yes | Yes | `""` |
| `number` | Yes | Yes | `0` |
| `boolean` | Yes | Yes | `False` |
| `object` | Yes | NO | `""` |
| `date` | Yes | Yes | `""` |
| `id` | Yes | Yes | `""` |
| `list[T]` | Yes | NO | `[]` |

Rules:
- Mutable variables MUST have an inline default value (e.g., `= ""`)
- Linked variables MUST have a `source:` and CANNOT have an inline default
- Linked variables CANNOT use `object` or `list` types
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

### 3.7 Knowledge Block

```
knowledge:
   citations_enabled: True
```

### 3.8 Start Agent

Exactly one `start_agent` entry point per agent:
```
start_agent: topic_selector
```

This names the topic that handles the first user message.

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
      inputs:
         subject: string
            description: "Case subject"
         desc_text: string
            description: "Case description"
      outputs:
         case_id: string
            description: "Created case ID"
            is_displayable: True
            is_used_by_planner: True
```

Target protocols:
- `flow://Flow_Api_Name` -- Autolaunched Flow
- `apex://ClassName` -- Apex @InvocableMethod (NO GenAiFunction registration needed)
- `externalService://ServiceName.operationName` -- External Service
- `generatePromptResponse://TemplateName` -- Prompt Template

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
- Use `set @variables.target = @outputs.source` for output capture
- Use `with param = ...` for LLM slot-filling (extracts from conversation)
- Use `available when @variables.x == True` for conditional visibility

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

   after_reasoning:
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
| Exactly one `start_agent` block | Multiple `start_agent:` entries | Single `start_agent: topic_name` |
| No comment-only if bodies | `if @variables.x:` with only `# comment` | Add executable statement: `\| text`, `run`, `set`, or `transition` |
| `connection` not `connections` | `connections messaging:` | `connection messaging:` |
| No `@inputs` in `set` clauses | `set @variables.x = @inputs.y` | Use `@outputs.y` or `@utils.setVariables` |
| No `default:` sub-property on variables | `order_id: mutable string` + `default: ""` | `order_id: mutable string = ""` (inline default) |
| No nested `type:` in action I/O | `order_id:` + `type: string` | `order_id: string` (inline type) |

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
| Structure & Syntax | 20 | All required blocks present (`config`, `system`, `start_agent`, at least one `topic`). Proper nesting. Clean indentation. No mixed tabs/spaces. Valid field names. |
| Deterministic Logic | 25 | `after_reasoning` patterns for post-action routing. FSM transitions with no dead-end topics. `available when` guards for security-sensitive actions. Post-action checks at TOP of `instructions: ->`. |
| Instruction Resolution | 20 | Clear, actionable instructions. Procedural mode (`->`) where conditionals are needed. Literal mode (`\|`) where static text suffices. Variable injection where dynamic. Conditional instructions based on state. |
| FSM Architecture | 15 | Hub-and-spoke or verification gate pattern. Every topic reachable. Every topic has an exit (transition or escalation). No orphan topics. Start topic routes correctly. |
| Action Configuration | 10 | Proper Level 1 definitions with targets and I/O schemas. Correct Level 2 invocations with `with`/`set`. Slot-filling (`...`) for conversational inputs. Output capture into variables. |
| Deployment Readiness | 10 | Valid `default_agent_user`. `developer_name` matches folder. `bundle-meta.xml` present. Correct `agent_type`. Linked variables for service agents (`EndUserId`, `RoutableId`, `ContactId`). |

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
start_agent: topic_selector

topic topic_selector:
   description: "Route based on user intent"
   reasoning:
      instructions: |
         Determine what the customer needs and route accordingly.
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

### Verification Gate

Users must pass through identity verification before accessing protected topics.
Use when handling sensitive data, payments, or PII.

```
start_agent: entry

topic entry:
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
   agent_type: "AgentforceServiceAgent"

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

start_agent: greeting

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
   agent_type: "AgentforceServiceAgent"

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

start_agent: router

topic router:
   label: "Main Router"
   description: "Determine customer intent and route to the right topic"
   reasoning:
      instructions: |
         Determine what the customer needs:
         - Order status or tracking -> order_support
         - Returns or refunds -> return_support
         - General questions -> general_support
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

         back: @utils.transition to @topic.router
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

         back: @utils.transition to @topic.router
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
         back: @utils.transition to @topic.router
            description: "Return to main menu"

topic confirmation:
   label: "Confirmation"
   description: "Confirm the completed action"
   reasoning:
      instructions: ->
         | Your request has been processed. Reference: {!@variables.case_id}
         | Is there anything else I can help with?
      actions:
         new_request: @utils.transition to @topic.router
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

For advanced cases beyond this skill's inline syntax, consult:

| Need | Reference |
|------|-----------|
| Credit consumption, lifecycle hooks, supervision, limits | `references/production-gotchas.md` |
| Which properties work in which contexts | `references/feature-validity.md` |
| Agent Script to Lightning type mapping | `references/complex-data-types.md` |
| Preview smoke test loop (Phase 3.5 rapid feedback) | `references/preview-test-loop.md` |
| Action definitions, targets, I/O binding, troubleshooting | `references/actions-reference.md` |
| How instructions resolve at runtime (3-phase model) | `references/instruction-resolution.md` |
| Reading traces, diagnosing issues, jq recipes | `references/debugging-guide.md` |
| Tracked platform issues and workarounds | `references/known-issues.md` |

---

## 13. TEMPLATE ASSETS

Pre-built templates in `assets/` for common patterns:

| Template | Description | File |
|----------|-------------|------|
| Hello World | Minimal single-topic agent | `assets/hello-world.agent` |
| Multi-Topic | Two topics with routing | `assets/multi-topic.agent` |
| Verification Gate | Identity verification before protected topics | `assets/verification-gate.agent` |
| Hub-and-Spoke | Central router with specialized spokes | `assets/hub-and-spoke.agent` |
| Lennar Home Search | Complex real-world agent with flows | `assets/lennar-home-search.agent` |
| Bundle Metadata | Companion XML template | `assets/metadata/bundle-meta.xml` |

When generating a new agent, start from the template closest to the user's requirements,
then customize. Always read the template file before generating to ensure you follow
the latest syntax patterns.

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
