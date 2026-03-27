# Agent Spec: {Agent Name}

> This spec is the ground truth for evaluating the agent across all ADLC lifecycle steps.
> Every section below becomes evaluation criteria — if the spec says it, the agent must do it.

## 1. Business Context

- **Company/Brand**: {who owns this agent}
- **End Users**: {who interacts with it — customers, employees, partners}
- **Business Problem**: {what problem does this agent solve}
- **Success Metric**: {how do we know it's working — containment rate, resolution time, CSAT}

## 2. Agent Identity

- **Agent Name**: {display name}
- **Persona**: {e.g., "friendly store associate", "professional concierge", "efficient IT support"}
- **AI Disclosure**: {how it identifies as AI — required for all agents}
- **Brand Voice**: {formal/casual/empathetic, specific tone guidelines}
- **Languages**: {supported languages}

## 3. Topics & Routing

List every topic the agent handles. For each topic:

### Topic: {topic_name}
- **Description**: {what triggers this topic — keywords, intents}
- **Entry conditions**: {any verification gates or prerequisites}
- **Actions**:
  - `{action_name}` — {what it does}
    - Target: `{flow://... or apex://...}`
    - Inputs: {param: type, param: type}
    - Outputs: {param: type}
- **Exit paths**: {where does the user go after — back to router, escalation, another topic}
- **Example utterances**:
  - "{example 1}"
  - "{example 2}"

### Router (start_agent)
- **Behavior**: Route only — do NOT answer questions directly
- **Routing strategy**: {hub-and-spoke, linear, hybrid}
- **Ambiguous intent handling**: {ask clarifying question, default to X topic}

## 4. Verification & Security Gates

- **What requires verification**: {e.g., "employee ID before HR actions", "room number before orders"}
- **Verification method**: {e.g., "ask for ID then call set_associate", "check variable is set"}
- **Gating pattern**: {available when guards, variable checks}

## 5. Scenarios (Expected Conversations)

For each key scenario, define the expected conversation flow:

### Scenario: {name}
- **Goal**: {what the user wants to accomplish}
- **Happy path turns**:
  1. User: "{utterance}" → Topic: {expected_topic}, Action: {expected_action}
  2. User: "{utterance}" → Action: {expected_action}
- **Expected outcome**: {task-completed, escalated, clarification-given}
- **Max turns**: {N}

### Scenario: {edge case name}
- **Goal**: {test boundary behavior}
- **Turns**:
  1. User: "{ambiguous or off-topic utterance}" → Behavior: {asks-clarifying-question, deflects}
- **Expected outcome**: {clarification-given, deflected}

## 6. Safety & Guardrails

- **Must NEVER do**: {list of absolute prohibitions}
- **Escalation triggers**: {when to hand off to human}
- **Domain boundaries**: {what the agent explicitly won't help with}
- **Regulatory requirements**: {HIPAA, PCI, financial regulations, etc.}
- **Data handling**: {what PII is collected, how it's used, what's NOT collected}

## 7. Actions & Integrations

Full action inventory with target details:

| Action | Target | Inputs | Outputs | Available When |
|--------|--------|--------|---------|----------------|
| {name} | {flow://... or apex://...} | {params} | {params} | {guard condition or "always"} |

## 8. Variables

| Variable | Type | Mutable/Linked | Purpose | Initial Value |
|----------|------|----------------|---------|---------------|
| {name} | {text/object/boolean} | {mutable/linked} | {what it's for} | {default} |

---

## Lifecycle Step Specs

### Authoring Spec
- **FSM pattern**: {hub-and-spoke, linear, hybrid}
- **Topic count**: {N topics + start_agent}
- **Action count**: {N actions total}
- **Key patterns**: {after_reasoning, available when, slot-filling, verification gates}
- **Evaluation focus**: Does the generated .agent file match sections 2-8 above?

### Testing Spec
- **Smoke test utterances**: {minimum N per topic}
- **Scenario coverage**: {all scenarios from section 5 must pass}
- **Grounding requirement**: {minimum % of utterances must be GROUNDED}
- **Safety probes**: {adversarial utterances that must be deflected}
- **Evaluation focus**: Does the agent route correctly, invoke right actions, stay grounded?

### Optimization Spec
- **Known issues to find**: {SMALL_TALK on intermediate actions, deflection on gated topics}
- **STDM signals to check**: {low quality scores, high retry rates, topic misroutes}
- **Fix validation**: {re-test failing utterances after fix, no regressions on passing ones}
- **Evaluation focus**: Does the optimizer find real issues and fix them without breaking other topics?
