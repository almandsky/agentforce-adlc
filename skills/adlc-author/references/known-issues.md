<!-- Parent: adlc-author/SKILL.md -->
# Known Issues

> Tracked issues, workarounds, and status for Agent Script and Agentforce platform.

---

## Issue Template

Each issue follows this format:

```
### Issue N: <Title>
- **Status**: Open / Fixed in TDD-XXX / Workaround available
- **Symptom**: What the user or developer observes
- **Root Cause**: Why it happens
- **Workaround**: How to avoid or mitigate
- **Affects**: Which agent types, CLI versions, or org editions
```

---

## Active Issues

### Issue 1: `require_user_confirmation` Compiles but Is a Runtime No-Op

- **Status**: Open
- **Symptom**: Setting `require_user_confirmation: True` on an action definition compiles and publishes without error, but the agent never prompts the user for confirmation before executing the action.
- **Root Cause**: The confirmation UX is not yet implemented in the runtime for AiAuthoringBundle-path agents. The compiler accepts the property because it's part of the schema, but the runtime ignores it.
- **Workaround**: Implement confirmation manually in the Agent Script using a two-step pattern:
  ```
  # Step 1: Collect intent and confirm
  reasoning:
     instructions: ->
        if @variables.pending_action == "refund" and @variables.confirmed == False:
           | I'll process a refund of {!@variables.amount}. Please confirm by saying "yes".

  # Step 2: Execute only after confirmation
     actions:
        process_refund: @actions.issue_refund
           description: "Process the refund"
           available when @variables.confirmed == True
           with amount = @variables.amount
  ```
- **Affects**: All agent types using AiAuthoringBundle path

### Issue 2: Canvas View Changes Supervision to Handoff

- **Status**: Open
- **Symptom**: After adding ANY new action in the Agent Builder Canvas view, existing `@topic.X` (supervision) references are silently converted to `@utils.transition to @topic.X` (handoff) transitions.
- **Root Cause**: The Canvas view serializer does not distinguish between supervision delegation and handoff transitions. When it re-serializes the agent, all topic references are normalized to transitions.
- **Workaround**: Do not mix Agent Script editing with Canvas view editing. If you must use Canvas, re-verify all `@topic.X` supervision references after saving and manually revert any that were changed to `@utils.transition`.
- **Affects**: All agent types when using Canvas view alongside Agent Script

### Issue 3: Chained Actions with Prompt Templates Fail Input Mapping

- **Status**: Open
- **Symptom**: When chaining a Prompt Template action after another action using `run @actions.prompt_action`, the Prompt Template doesn't receive inputs correctly. The `Input:Query` format used internally doesn't map to the chained context.
- **Root Cause**: Prompt Template actions use a different input mapping mechanism (`Input:Query`) that is not compatible with the standard `with` binding used in action chaining.
- **Workaround**: Do not chain Prompt Template actions. Instead, use a separate (non-chained) action invocation:
  ```
  # WRONG -- chained prompt template
  process: @actions.get_data
     run @actions.summarize_prompt_template
     with query = @outputs.data

  # CORRECT -- separate invocations
  fetch_data: @actions.get_data
     set @variables.raw_data = @outputs.data

  summarize: @actions.summarize_prompt_template
     with query = @variables.raw_data
  ```
- **Affects**: Prompt Template targets only

### Issue 4: `else if` Not Supported

- **Status**: By design (not a bug)
- **Symptom**: `else if` causes a compiler error. Nested `if` inside `else:` also fails.
- **Root Cause**: Agent Script's grammar does not include `else if` as a construct. The language supports only `if`, `else:`, and compound conditions.
- **Workaround**: Use compound conditions or sequential flat `if` statements:
  ```
  # WRONG
  if @variables.tier == "gold":
     | Gold treatment
  else if @variables.tier == "silver":
     | Silver treatment

  # CORRECT -- sequential flat ifs
  if @variables.tier == "gold":
     | Gold treatment
  if @variables.tier == "silver":
     | Silver treatment
  if @variables.tier != "gold" and @variables.tier != "silver":
     | Standard treatment
  ```
- **Affects**: All agents

### Issue 5: Linked Variables Empty in Preview

- **Status**: By design (preview limitation)
- **Symptom**: Linked variables (`source: @MessagingSession.*`, `source: @MessagingEndUser.*`) are always empty/null when testing with `sf agent preview`.
- **Root Cause**: The preview API creates an isolated session without a messaging channel context. Linked variables require a live messaging session to resolve their `source:` bindings.
- **Workaround**: Use mutable test variables with hardcoded defaults for preview testing. See `preview-test-loop.md` for the full workaround pattern. For full context-variable testing, use the Runtime API instead of preview.
- **Affects**: All service agents using linked variables

### Issue 6: `output_instructions` Property Status Unknown

- **Status**: Untested
- **Symptom**: The `output_instructions:` property compiles on action definitions but its runtime behavior has not been verified.
- **Root Cause**: Property exists in the schema but may not be processed by the current runtime.
- **Workaround**: Do not rely on `output_instructions:` for critical behavior. Instead, put output formatting guidance in the topic's `reasoning: instructions:` block.
- **Affects**: All agent types

### Issue 7: `always_expect_input` Not Implemented

- **Status**: Open (not implemented)
- **Symptom**: The `always_expect_input:` property is referenced in some documentation but is not recognized by the Agent Script compiler.
- **Root Cause**: The property was planned but not implemented in the current compiler version.
- **Workaround**: No workaround needed -- just don't use this property. If you need the agent to always wait for user input, add explicit instructions: "Always wait for the customer to respond before taking action."
- **Affects**: All agents

### Issue 8: `run` in `after_reasoning` Has Inconsistent Behavior

- **Status**: Open
- **Symptom**: Using `run @actions.X` inside `after_reasoning:` works in some bundle types but silently fails in others. The action may not execute or may execute with stale variable values.
- **Root Cause**: The `after_reasoning:` runtime processor handles `set`, `if`/`else`, and `transition to` reliably, but `run` invokes the action runtime which has inconsistent support in the post-reasoning phase.
- **Workaround**: Move `run` calls to `reasoning: instructions: ->` (as a deterministic pre-LLM action) or use `reasoning: actions:` (as an LLM-driven action). Keep `after_reasoning:` for `set`, `if`/`else`, and `transition to` only.
  ```
  # RISKY -- run in after_reasoning
  after_reasoning:
     run @actions.create_record
        with data = @variables.collected_data
        set @variables.record_id = @outputs.id

  # SAFER -- Use after_reasoning only for transition
  after_reasoning:
     if @variables.all_fields_collected == True:
        transition to @topic.create_and_confirm
  ```
- **Affects**: Varies by bundle type; most common with AiAuthoringBundle

### Issue 9: VS Code Source Tracking Unsupported for AiAuthoringBundle

- **Status**: Open
- **Symptom**: `sf project retrieve start` and `sf project deploy start` with source tracking fail with: `UnsupportedBundleTypeError: Unsupported Bundle Type: AiAuthoringBundle`
- **Root Cause**: The Salesforce VS Code extension's source tracking feature doesn't recognize AiAuthoringBundle as a supported metadata type.
- **Workaround**: Use explicit CLI commands instead of source tracking:
  ```bash
  # Retrieve
  sf project retrieve start -m AiAuthoringBundle:MyAgent -o TargetOrg

  # Deploy (use publish, not deploy)
  sf agent publish authoring-bundle --api-name MyAgent -o TargetOrg
  ```
- **Affects**: All developers using VS Code with Salesforce Extensions

### Issue 10: Hebrew and Indonesian Appear Twice in Language Dropdown

- **Status**: Open
- **Symptom**: In the Setup UI language configuration, Hebrew and Indonesian each appear twice in the dropdown list.
- **Root Cause**: Duplicate entries in the locale metadata.
- **Workaround**: Always select from the FIRST occurrence. Selecting the second occurrence causes save errors.
- **Affects**: Agents with multi-language configuration

### Issue 11: bundle-meta.xml Extra Fields Cause Deploy Errors

- **Status**: By design
- **Symptom**: Adding fields like `<developerName>`, `<masterLabel>`, `<description>`, or `<target>` to `bundle-meta.xml` causes "Required fields are missing: [BundleType]" errors on deploy.
- **Root Cause**: The Metadata API deploy step fails when unexpected fields are present in the bundle metadata. The `sf agent publish authoring-bundle` command manages these fields automatically.
- **Workaround**: Keep `bundle-meta.xml` minimal -- only `<bundleType>AGENT</bundleType>`:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <AiAuthoringBundle xmlns="http://soap.sforce.com/2006/04/metadata">
    <bundleType>AGENT</bundleType>
  </AiAuthoringBundle>
  ```
- **Affects**: All agents using AiAuthoringBundle path

### Issue 12: Publish Does Not Activate

- **Status**: By design
- **Symptom**: After `sf agent publish authoring-bundle` succeeds, the agent is not automatically activated. Preview and runtime calls fail with "No valid version available."
- **Root Cause**: Publishing creates a new version but does not make it the active version. Activation is a separate step.
- **Workaround**: Always run activation after publish:
  ```bash
  sf agent publish authoring-bundle --api-name MyAgent -o Org --json
  sf agent activate --api-name MyAgent -o Org
  ```
- **Affects**: All agents

### Issue 13: `duplicate value found: GenAiPluginDefinition` on Publish

- **Status**: Root cause identified
- **Symptom**: `sf agent publish authoring-bundle` fails with `duplicate value found: GenAiPluginDefinition duplicates value on record with id: <topic_name>_<planner_id>`.
- **Root Cause**: Two known causes:
  1. **`start_agent` and `topic` share the same name.** Both create `GenAiPluginDefinition` records. If `start_agent: entry` and `topic entry:` coexist, publish tries to create two records named `entry` and fails. Each failed attempt leaves an orphaned record, compounding the problem.
  2. **Orphaned records from previous failed publishes.** Even after fixing the name collision, prior orphans still exist. They cannot be deleted (DML not allowed, REST returns dependency errors).
- **Fix** (preventive): Give `start_agent` and all `topic` blocks unique names:
  ```
  # WRONG — causes duplicate GenAiPluginDefinition
  start_agent: entry
  topic entry:

  # CORRECT — different names
  start_agent router:
  topic welcome:
  ```
- **Workaround** (if orphans already exist): Rename the colliding topic to a name that has no orphaned records:
  ```bash
  # 1. Check how many orphans exist
  sf data query --query "SELECT Id, DeveloperName FROM GenAiPluginDefinition WHERE MasterLabel = 'Entry'" -o Org --json
  # 2. Rename the topic in the .agent file (e.g., entry -> welcome)
  # 3. Re-publish with the new name
  sf agent publish authoring-bundle --api-name MyAgent -o Org --json
  ```
  Note: `sf project deploy start` does NOT clean up orphans. Only renaming avoids the collision.
- **Affects**: All agents where `start_agent` name matches a `topic` name

### Issue 14: `@inputs` Not Valid in `set` Clauses

- **Status**: By design
- **Symptom**: Using `set @variables.X = @inputs.Y` in a Level 2 invocation causes a compiler error.
- **Root Cause**: The `@inputs` namespace refers to the action's input parameters, which are only available for reading in the context of the action execution. The `set` clause captures outputs, so only `@outputs.Y` is valid.
- **Workaround**: Use `@outputs.Y` in `set` clauses. If you need to capture an input value, have the action echo it as an output:
  ```
  # WRONG
  set @variables.x = @inputs.order_id

  # CORRECT
  set @variables.x = @outputs.order_id
  ```
- **Affects**: All agents

### Issue 15: Comment-Only If Bodies Cause Compiler Error

- **Status**: By design
- **Symptom**: An `if` block containing only a comment (e.g., `# TODO: implement`) causes a compiler error.
- **Root Cause**: The compiler requires at least one executable statement in every `if` body.
- **Workaround**: Add a no-op executable statement:
  ```
  # WRONG
  if @variables.debug == True:
     # TODO: add debug logging

  # CORRECT
  if @variables.debug == True:
     | Debug mode enabled.
  ```
- **Affects**: All agents

### Issue 16: Topic Selector Re-Entry After User Provides Missing Input

- **Status**: Open
- **Symptom**: After the topic selector asks for clarification and the user provides the missing input, the topic selector doesn't properly re-evaluate and route to the correct topic. Instead, it stays in the selector or routes to the wrong topic.
- **Root Cause**: The topic selector's re-resolution logic doesn't always incorporate the new user input into its routing decision.
- **Workaround**: Use the latch variable pattern to force re-entry to the correct topic:
  ```
  variables:
     pending_topic: mutable string = ""

  topic topic_selector:
     reasoning:
        instructions: ->
           if @variables.pending_topic == "orders":
              transition to @topic.order_support
           | How can I help you?
        actions:
           to_orders: @actions.set_pending_topic
              description: "Route to orders"
              with topic = "orders"
              set @variables.pending_topic = @outputs.topic
  ```
- **Affects**: All agents with topic selector routing

### Issue 17: Loop Protection Guardrail Limits Iterations

- **Status**: By design
- **Symptom**: After 3-4 iterations of the post-action loop (Phase 1 re-resolution), the agent breaks out of the current topic and returns to the topic selector.
- **Root Cause**: Built-in guardrail to prevent infinite loops. The limit is approximately 3-4 iterations per topic entry.
- **Workaround**: Design data collection flows to collect all needed fields in a single action call (using slot-filling with `...`) rather than collecting fields one at a time in a loop. If you need more iterations, use multiple topics with transitions between them.
- **Affects**: All agents

### Issue 18: Multiplication and Division Not Supported in Expressions

- **Status**: By design
- **Symptom**: Using `*`, `/`, or `%` operators in `if` conditions or `set` statements causes compiler errors.
- **Root Cause**: Agent Script's expression evaluator only supports `+`, `-` for arithmetic. More complex math must be done in Flow or Apex.
- **Workaround**: Move calculations to a Flow or Apex action and return the result as an output:
  ```
  # WRONG
  set @variables.total = @variables.price * @variables.quantity

  # CORRECT -- Use a Flow/Apex action
  calculate: @actions.calculate_total
     with price = @variables.price
     with quantity = @variables.quantity
     set @variables.total = @outputs.total
  ```
- **Affects**: All agents

### Issue 19: `set` and Post-Action Operations Only Work on `@actions.X`

- **Status**: By design
- **Symptom**: Adding `set @variables.X = @outputs.Y` on `@utils.transition` or `@utils.escalate` invocations causes a compiler error or is silently ignored.
- **Root Cause**: Framework utility actions (`@utils.*`) do not produce outputs. The `set` clause only works on user-defined actions that have `outputs:` blocks.
- **Workaround**: If you need to set a variable before transitioning, use a separate `set` statement or a `@utils.setVariables` action:
  ```
  # WRONG
  go_next: @utils.transition to @topic.next
     set @variables.route = "next"

  # CORRECT -- set before transition
  after_reasoning:
     set @variables.route = "next"
     transition to @topic.next
  ```
- **Affects**: All agents

### Issue 20: Tooling API PATCH Required for Instruction Updates When Publish Fails

- **Status**: Open (workaround documented)
- **Symptom**: After editing the `.agent` file and running `sf agent publish authoring-bundle`, the live `GenAiPluginInstructionDef` records are not updated. The agent continues to use old instructions.
- **Root Cause**: The publish process sometimes fails to propagate instruction changes to the `GenAiPluginInstructionDef` records, especially after previous failed publishes or when orphaned drafts exist.
- **Workaround**: Use the Tooling API to directly PATCH the instruction records:
  ```bash
  # Get the InstructionDef ID
  sf data query \
    --query "SELECT Id, Description FROM GenAiPluginInstructionDef WHERE GenAiPluginDefinitionId = '<topic_id>'" \
    -o Org --json

  # Patch the instruction text
  sf api request rest \
    "/services/data/v63.0/tooling/sobjects/GenAiPluginInstructionDef/<id>" \
    --method PATCH \
    --body '{"Description": "New instruction text here"}' \
    -o Org
  ```
  A successful PATCH returns HTTP 204 No Content. The Tooling API field name is `Description` (the SOQL field name on the same object is `Instruction`).
- **Affects**: All agents (more common after failed publishes)

---

## Contributing

When you encounter a new issue with Agent Script or the Agentforce platform:

1. **Check this list first** -- the issue may already be documented with a workaround.
2. **If new**, add it using the Issue Template format above.
3. **Include**:
   - Exact error message or unexpected behavior
   - Minimal reproduction steps
   - sf CLI version (`sf --version`)
   - Agent type (`AgentforceServiceAgent` or `AgentforceEmployeeAgent`)
   - Whether it's AiAuthoringBundle or GenAiPlannerBundle path
4. **Classify status**:
   - `Open` -- confirmed issue with no platform fix
   - `By design` -- intentional limitation
   - `Workaround available` -- has a reliable mitigation
   - `Fixed in TDD-XXX` -- resolved in a specific release
5. **Update existing issues** when new information is found (e.g., a workaround is discovered or the issue is fixed).
