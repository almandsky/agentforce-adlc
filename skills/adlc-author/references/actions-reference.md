<!-- Parent: adlc-author/SKILL.md -->
# Actions Reference

> Complete reference for action definitions, invocations, targets, and I/O binding in Agent Script.

---

## 1. Action Properties Reference

### Level 1: Action Definitions (inside `topic > actions:`)

Action definitions declare WHAT an action is -- its target, inputs, and outputs.

```
topic my_topic:
   actions:
      my_action:
         label: "My Action"
         description: "What this action does"
         target: "flow://My_Flow_Api_Name"
         require_user_confirmation: True
         include_in_progress_indicator: True
         progress_indicator_message: "Working on it..."
         inputs:
            order_id: string
               label: "Order ID"
               description: "The order identifier"
               is_required: True
               is_user_input: False
         outputs:
            status: string
               label: "Order Status"
               description: "Current order status"
               is_displayable: True
               is_used_by_planner: True
               filter_from_agent: False
```

**Action-Level Properties:**

| Property | Type | Required | Effect |
|---|---|---|---|
| `description` | String | Yes | LLM reads this to decide when to invoke the action |
| `label` | String | No | Display name in UI |
| `target` | String | Yes | Protocol + API name of the action target |
| `require_user_confirmation` | Boolean | No | Compile-valid; runtime behavior may be a no-op (known issue) |
| `include_in_progress_indicator` | Boolean | No | Shows a spinner during execution |
| `progress_indicator_message` | String | No | Custom text for the spinner |

**Input Properties:**

| Property | Type | Default | Effect |
|---|---|---|---|
| (inline type) | -- | Required | Data type: `string`, `number`, `boolean`, `date`, `id`, `list`, `object`, `currency`, `datetime` |
| `description` | String | -- | Explains the parameter to the LLM |
| `label` | String | -- | Display name in UI |
| `is_required` | Boolean | `False` | Marks input as mandatory |
| `is_user_input` | Boolean | `False` | LLM extracts value from conversation context |
| `complex_data_type_name` | String | -- | Lightning type mapping (see `complex-data-types.md`) |

**Output Properties:**

| Property | Type | Default | Effect |
|---|---|---|---|
| (inline type) | -- | Required | Data type (same options as input) |
| `description` | String | -- | Explains the output to the LLM |
| `label` | String | -- | Display name in UI |
| `is_displayable` | Boolean | `True` | `False` hides from user display |
| `is_used_by_planner` | Boolean | `False` | `True` lets the LLM reason about the value |
| `filter_from_agent` | Boolean | `False` | `True` hides from user display (GA standard name) |
| `developer_name` | String | -- | Overrides the parameter's API name |
| `complex_data_type_name` | String | -- | Lightning type mapping |

> **Note**: `filter_from_agent: True` and `is_displayable: False` are equivalent. `filter_from_agent` is the GA standard. See `production-gotchas.md` for the zero-hallucination routing pattern.

### Level 2: Action Invocations (inside `topic > reasoning > actions:`)

Action invocations declare HOW to call a Level 1 action -- parameter bindings, output capture, and visibility guards.

```
reasoning:
   actions:
      run_lookup: @actions.my_action
         description: "Look up order details"
         with order_id = @variables.order_id
         with tracking_num = ...
         set @variables.order_status = @outputs.status
         available when @variables.order_id != ""
```

**Invocation Properties:**

| Property | Required | Effect |
|---|---|---|
| `@actions.X` reference | Yes | Links to the Level 1 definition |
| `description` | Yes | LLM reads this to decide when to invoke |
| `with param = value` | No | Input binding. Value can be `@variables.X`, a literal, or `...` (slot-filling) |
| `set @variables.X = @outputs.Y` | No | Output capture into a mutable variable |
| `available when condition` | No | Guards when the action is visible to the LLM |

**CRITICAL rules for Level 2:**
- Use `with`/`set` syntax, NOT `inputs:`/`outputs:` blocks
- The `...` token means "LLM extracts from conversation" (slot-filling)
- Only `@actions.X` references support `set` clauses (not `@utils.X`)
- Multiple `available when` clauses on the same action are AND-ed together

---

## 2. Action Target Types

| # | Target Protocol | Format | Example | Notes |
|---|---|---|---|---|
| 1 | Autolaunched Flow | `flow://Flow_Api_Name` | `flow://Get_Order_Status` | Most common. Flow must be Autolaunched (not Screen Flow). |
| 2 | Apex InvocableMethod | `apex://ClassName` | `apex://OrderProcessor` | Uses `@InvocableMethod` annotation. No GenAiFunction registration needed when using AiAuthoringBundle path. |
| 3 | External Service | `externalService://ServiceName.operationName` | `externalService://StripeAPI.createCharge` | Requires Named Credential + External Service registration in Setup. |
| 4 | Prompt Template | `generatePromptResponse://TemplateName` | `generatePromptResponse://Summarize_Case` | Invokes a Prompt Template. Costs 2-16 credits depending on complexity. |
| 5 | Retriever (Knowledge) | `retriever://RetrieverName` | `retriever://SearchKnowledgeBase` | Searches a DataKnowledgeSpace. |
| 6 | MuleSoft API | `externalService://MuleSoft_Service.operation` | `externalService://Inventory_API.checkStock` | Via External Service + MuleSoft Anypoint connector. |
| 7 | Heroku Function | `flow://Invoke_Heroku_Function` | `flow://Call_ML_Model` | Wrapped in a Flow that calls the Heroku endpoint. |
| 8 | Platform Event | `flow://Publish_Platform_Event` | `flow://Publish_OrderUpdated` | Flow publishes the event; agent doesn't wait for response. |
| 9 | Custom Notification | `flow://Send_Custom_Notification` | `flow://Notify_Manager` | Flow sends a custom notification via `CustomNotificationType`. |
| 10 | Screen Flow (Indirect) | `flow://Wrapper_Flow` | -- | Screen Flows cannot be called directly. Wrap in an Autolaunched Flow. |
| 11 | Record-Triggered Flow | Not directly callable | -- | Use `flow://` to call an Autolaunched Flow that performs the same DML to trigger it. |
| 12 | Salesforce Connect (OData) | `externalService://` | -- | Via External Service + Salesforce Connect registration. |
| 13 | Einstein OCR | `flow://OCR_Flow` | `flow://Extract_Invoice_Data` | Flow wraps the Einstein OCR API. |
| 14 | Einstein Sentiment | `flow://Sentiment_Flow` | `flow://Analyze_Sentiment` | Flow wraps the Einstein Sentiment API. |
| 15 | Data Cloud Query | `apex://DataCloudQueryService` | -- | Apex class runs ANSI SQL against Data Cloud DMOs. |
| 16 | SOQL Query | `apex://SOQLQueryService` or `flow://` | -- | Apex or Flow that performs SOQL and returns results. |
| 17 | REST Callout | `apex://RestCalloutService` | -- | Apex class makes HTTP callout via Named Credential. |
| 18 | SOAP Callout | `apex://SoapCalloutService` | -- | Apex class makes SOAP callout. |
| 19 | Einstein Copilot Action | Varies by action type | -- | Built-in actions (e.g., `QueryRecords`) use the legacy GenAiPlannerBundle path. |
| 20 | Commerce Cloud API | `externalService://` | -- | Via External Service + Commerce Cloud connector. |
| 21 | Slack Action | `flow://Post_Slack_Message` | -- | Flow wraps the Slack Conversations API. |
| 22 | Email Action | `flow://Send_Email_Alert` | -- | Flow uses an Email Alert or Messaging action. |

> **Target protocol prefix must be lowercase**: `flow://`, `apex://`, `externalService://`, `generatePromptResponse://`, `retriever://`. Uppercase protocol prefixes cause compile errors.

---

## 3. Action Invocation Methods

### Method 1: LLM-Driven (reasoning.actions block)

The LLM decides when to call the action based on the action's `description` and the current conversation context.

```
reasoning:
   actions:
      lookup_order: @actions.get_order_status
         description: "Look up order status when customer asks about their order"
         with order_id = ...
         set @variables.status = @outputs.status
```

**When to use**: Most actions. The LLM matches the user's intent to the action description.

### Method 2: Deterministic (instructions: -> with `run`)

The action runs unconditionally (or conditionally via `if`) during instruction resolution, before or after the LLM reasoning step.

```
reasoning:
   instructions: ->
      # Pre-LLM: Load data deterministically
      run @actions.load_customer_data
         with customer_id = @variables.customer_id
         set @variables.risk_score = @outputs.risk_score

      # Dynamic instructions based on loaded data
      | Customer risk score: {!@variables.risk_score}
```

**When to use**: Data loading, pre-computation, post-action routing. Use when the action MUST run regardless of what the user said.

### Method 3: Deterministic (after_reasoning)

The action runs deterministically after the LLM has produced its response.

```
after_reasoning:
   if @variables.case_subject != "" and @variables.case_description != "":
      run @actions.create_case
         with subject = @variables.case_subject
         with description = @variables.case_description
         set @variables.case_id = @outputs.case_id
   if @variables.case_id != "":
      transition to @topic.confirmation
```

**When to use**: Record creation after the LLM has collected all required fields. Post-action routing. Audit logging.

---

## 4. Flow Actions Implementation

Flow is the most common action target type. Requirements for a Flow to work as an agent action:

### Flow Requirements

| Requirement | Details |
|---|---|
| Type | Must be **Autolaunched Flow** (not Screen Flow, not Record-Triggered) |
| Active | Flow must be active in the target org |
| API Name | Referenced by `flow://Api_Name` in the target |
| Input Variables | Must match the `inputs:` block in the action definition (name and type) |
| Output Variables | Must match the `outputs:` block in the action definition |
| Available for Agents | Enable "Make Available for Agents" in Flow Builder settings |

### Input/Output Name Matching

Flow variable names MUST match the action definition I/O names exactly (case-sensitive):

```
# Agent Script action definition:
inputs:
   order_id: string
      description: "Order ID"

# Flow must have an input variable named exactly: order_id (type: Text)
```

If names don't match, the action will compile but fail at runtime with empty inputs or missing outputs.

### Flow Variable Type Mapping

| Agent Script Type | Flow Variable Type |
|---|---|
| `string` | Text |
| `number` | Number |
| `boolean` | Boolean |
| `date` | Date |
| `datetime` | Date/Time |
| `id` | Text (Salesforce IDs are passed as text) |
| `currency` | Currency |
| `list[string]` | Text Collection |
| `object` | Record (SObject) |

---

## 5. Apex Actions

Apex classes can be used as action targets via the `@InvocableMethod` annotation.

### Path A: AiAuthoringBundle (Recommended)

When using the AiAuthoringBundle path (Agent Script `.agent` files), Apex actions **do not need GenAiFunction registration**. The action definition in the `.agent` file provides all the metadata the planner needs.

```java
public class OrderProcessor {
    @InvocableMethod(label='Process Order' description='Process a customer order')
    public static List<OrderResult> processOrder(List<OrderRequest> requests) {
        // Implementation
    }

    public class OrderRequest {
        @InvocableVariable(label='Order ID' required=true)
        public String order_id;

        @InvocableVariable(label='Customer ID')
        public String customer_id;
    }

    public class OrderResult {
        @InvocableVariable(label='Status')
        public String status;

        @InvocableVariable(label='Confirmation Number')
        public String confirmation_number;
    }
}
```

Agent Script definition:

```
actions:
   process_order:
      description: "Process a customer order"
      target: "apex://OrderProcessor"
      inputs:
         order_id: string
            description: "Order ID"
            is_required: True
         customer_id: string
            description: "Customer ID"
      outputs:
         status: string
            description: "Processing status"
            is_displayable: True
         confirmation_number: string
            description: "Order confirmation number"
            is_displayable: True
```

### Path B: GenAiPlannerBundle (Legacy)

The older GenAiPlannerBundle path requires registering Apex actions as `GenAiFunction` records in Setup > Einstein > Generative AI > Functions. This path is used by agents created in the UI (Agent Builder) rather than via Agent Script.

**Key differences from Path A:**
- Requires a `GenAiFunction` metadata record per action
- I/O schemas are defined in the `GenAiFunction`, not in Agent Script
- The planner reads metadata from `GenAiFunction` rather than the `.agent` file
- More complex to maintain (two sources of truth for I/O schemas)

**Recommendation**: Use Path A (AiAuthoringBundle) for all new agent development. Path B is only needed when integrating with legacy agents created before Agent Script was available.

---

## 6. I/O Name Matching Rules

Action input and output names must follow specific rules to work correctly across the Agent Script compiler, the planner, and the action target (Flow/Apex).

### Naming Rules

| Rule | Details |
|---|---|
| Case-sensitive | `order_id` and `Order_Id` are different names |
| Must match target | The input/output name in Agent Script must match the variable name in the Flow or `@InvocableVariable` name in Apex |
| No reserved words | Cannot use `description`, `label`, `is_required`, `is_displayable`, `is_used_by_planner` as I/O field names |
| Valid characters | Letters, numbers, underscores only. Must start with a letter. |
| No consecutive underscores | `order__id` is invalid; use `order_id` |
| Maximum 80 characters | Applies to both input and output names |

### Common Mismatches

| Agent Script | Flow Variable | Result |
|---|---|---|
| `order_id: string` | `order_id` (Text) | Correct -- names match |
| `order_id: string` | `OrderId` (Text) | **FAIL** -- case mismatch |
| `order_id: string` | `orderId` (Text) | **FAIL** -- underscore vs camelCase |
| `desc_text: string` | `desc_text` (Text) | Correct |
| `description: string` | `description` (Text) | **FAIL** -- `description` is a reserved word |

### I/O Type Coercion

The planner performs limited type coercion:

| Agent Script Type | Actual Value | Result |
|---|---|---|
| `string` | `123` (number) | Coerced to `"123"` |
| `number` | `"42"` (string) | Coerced to `42` |
| `boolean` | `"true"` (string) | Coerced to `True` |
| `string` | `null` | Passed as `""` (empty string) |
| `number` | `null` | Passed as `0` |

---

## 7. API Actions (External Service)

External Service actions call REST APIs through Named Credentials.

### Architecture

```
Agent Script target: "externalService://ServiceName.operationName"
       |
       v
Named Credential (auth, base URL)
       |
       v
External Service Registration (OpenAPI schema)
       |
       v
External REST API
```

### Setup Requirements

1. **Named Credential**: Configured in Setup with the API's base URL and authentication method (OAuth, API Key, etc.)
2. **External Service**: Registered in Setup > External Services by uploading the API's OpenAPI (Swagger) spec
3. **Permission Set**: The Einstein Agent User must have permission to call the External Service

### Agent Script Example

```
actions:
   check_inventory:
      description: "Check product inventory from external warehouse system"
      target: "externalService://WarehouseAPI.getInventory"
      inputs:
         product_sku: string
            description: "Product SKU"
            is_required: True
      outputs:
         quantity_available: number
            description: "Available stock quantity"
            is_displayable: True
         warehouse_location: string
            description: "Warehouse where stock is located"
```

---

## 8. Connection Block (Escalation Routing)

The `connection` block defines how the agent routes to human agents. This is specific to service agents (`AgentforceServiceAgent`).

### Basic Connection

```
connection messaging:
   adaptive_response_allowed: True
```

This enables the agent to respond over messaging channels with adaptive formatting.

### Escalation Routing (with Omni-Channel Flow)

```
connection messaging:
   outbound_route_type: "OmniChannelFlow"
   outbound_route_name: "flow://Route_From_Agent"
   escalation_message: "Let me connect you with a specialist who can help."
   adaptive_response_allowed: False
```

When `outbound_route_type` is present, ALL three route properties are required:
- `outbound_route_type` -- must be `"OmniChannelFlow"`
- `outbound_route_name` -- must reference a valid Omni-Channel routing Flow
- `escalation_message` -- the message shown to the user when escalating

### Escalation Action

In reasoning actions, use `@utils.escalate` to trigger escalation:

```
reasoning:
   actions:
      transfer_to_human: @utils.escalate
         description: "Transfer to a human agent"
         available when @variables.needs_human == True
```

Valid channel types for the `connection` block: `messaging`, `voice`, `web`.

---

## 9. GenAiFunction Metadata Summary

For reference, the `GenAiFunction` metadata object is the Salesforce-internal representation of an action. When using Agent Script (AiAuthoringBundle path), you generally do not interact with `GenAiFunction` directly -- the compiler generates it from your action definitions. However, understanding the structure helps with debugging.

| Field | Maps To | Notes |
|---|---|---|
| `DeveloperName` | Action definition name | Auto-generated by compiler |
| `MasterLabel` | Action `label:` or `description:` | Display name |
| `Description` | Action `description:` | LLM reads this for routing |
| `FunctionType` | Target protocol | `Flow`, `Apex`, `ExternalService`, etc. |
| `FunctionTarget` | Target API name | e.g., `Get_Order_Status` for `flow://Get_Order_Status` |
| `IsConfirmationRequired` | `require_user_confirmation:` | Boolean |
| Input Parameters | `inputs:` block | Stored as `GenAiFnParameter` child records |
| Output Parameters | `outputs:` block | Stored as `GenAiFnParameter` child records |

### Querying GenAiFunction (debugging)

```bash
# Find all actions for a specific agent
sf data query \
  --query "SELECT Id, DeveloperName, MasterLabel, Description FROM GenAiFunction WHERE DeveloperName LIKE '%MyAgent%'" \
  -o TargetOrg --json

# Find action parameters
sf data query \
  --query "SELECT Id, Name, DataType, IsInput, IsOutput FROM GenAiFnParameter WHERE GenAiFunctionId = '<action_id>'" \
  -o TargetOrg --json
```

---

## 10. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| "Internal Error" on publish | Missing `inputs:` or `outputs:` on a Level 1 action definition | Add complete I/O schemas to all action definitions with targets |
| Action compiles but never invoked by LLM | Action `description:` too vague or overlaps with another action | Make description specific: "Use this for X but not for Y" |
| Action invoked but returns empty outputs | I/O name mismatch between Agent Script and Flow/Apex | Ensure exact case-sensitive name match |
| `ACTION_ERROR` in trace | Flow/Apex runtime error (null pointer, validation rule, etc.) | Check the Flow's error handling; add fault paths |
| Wrong action selected | Multiple actions with similar descriptions | Add exclusion language to each description; use `available when` guards |
| Action visible when it shouldn't be | Missing or incorrect `available when` guard | Add `available when @variables.prerequisite == True` |
| `set` clause ignored on `@utils.transition` | `set` only works on `@actions.X` references | Move the variable assignment to a separate action or use `@utils.setVariables` |
| `with param = @inputs.X` compile error | Cannot reference `@inputs` in `set` or `with` clauses | Use `@outputs.X` for outputs or `@variables.X` for variables |
| Prompt Template action maps inputs incorrectly | Known issue with `Input:Query` format in chained actions | Use a separate (non-chained) action invocation for Prompt Templates |
| `duplicate value found: GenAiPluginDefinition` on publish | Orphaned draft from a previous failed publish | Use `sf project deploy start --metadata "AiAuthoringBundle:X"` as a fallback, then retry publish |
| Action I/O uses reserved word as name | `description`, `label`, etc. cannot be field names | Rename to `desc_text`, `label_text`, etc. |
| `is_required: True` not enforced | Runtime may not enforce required inputs | Add explicit checks in your Flow/Apex for null/empty values |
