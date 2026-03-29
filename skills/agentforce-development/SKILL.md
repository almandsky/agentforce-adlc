---
name: agentforce-development
description: Build, review, discover, scaffold, deploy, and ensure safety of Agentforce agents
allowed-tools: Bash Read Write Edit Glob Grep
metadata:
  argument-hint: "[describe your agent] | review <path> | discover <org> | scaffold <org> | deploy <org> | safety review <path>"
  license: proprietary
  compatibility: claude-code
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

- Batch testing or regression suites (use /agentforce-test)
- Analyzing production session traces (use /agentforce-observability)

---

## 2. WORKFLOW PHASES

### Phase 0: Safety Review (LLM-Driven)

Before generating any agent, evaluate the request against 7 safety categories:
Identity & Transparency, User Safety, Data Handling, Content Safety, Fairness,
Deception & Manipulation, Scope & Boundaries.

- Any BLOCK finding: **REFUSE** the request
- WARN findings only: **Ask clarifying questions** and propose mitigations
- Clean: Proceed to Phase 1

**Proactive safety additions for ALL agents:**
- AI disclosure in `system: instructions:`
- Scope boundaries ("Do not answer questions outside of X")
- Escalation path for sensitive topics
- Professional referral disclaimers for regulated domains

See [references/safety-review-reference.md](references/safety-review-reference.md) for the full 7-category review framework.

### Phase 1: Org Discovery

Auto-detect connected orgs:
```bash
sf org list --json 2>/dev/null
```
Present options to the user. If none connected, guide them through `sf org login web`.

### Phase 1b: Requirements & Use Case Discovery

**Do not jump straight to generating the agent.** Ask clarifying questions in rounds:

**Round 1 -- Business context:** What problem does this solve? Top 3 must-dos? What should it NEVER do?

**Round 2 -- Agent design:**
- Agent name (PascalCase), agent type (Service or Employee)
- Topics and what each handles
- Actions per topic (flow/apex/retriever targets)
- Variables (mutable vs linked), FSM pattern (hub-and-spoke, verification gate, linear)

**Round 3 -- Scenarios:** 2-3 example conversations, edge cases, escalation triggers.

Do not proceed until Rounds 1-2 are answered.

### Phase 2: Setup

**Step 0:** Ensure `sfdx-project.json` exists (create minimal one if missing).

**Step 1:** Query the Einstein Agent User:
```bash
sf data query -q "SELECT Username FROM User WHERE Profile.Name = 'Einstein Agent User' AND IsActive = true" -o <org> --json
```

### Phase 2b: Discover Existing Targets

Query the org for existing Flows and Apex classes before generating action definitions:
```bash
sf data query -q "SELECT ApiName, IsActive FROM FlowDefinitionView WHERE IsActive = true AND ProcessType = 'AutoLaunchedFlow'" -o <org> --json
sf api request rest "/services/data/v66.0/actions/custom/flow/<FlowApiName>" -o <org>
```
Use discovered parameters in Level 1 action definitions. Do NOT guess parameter names.

### Phase 3: Generate

Write the `.agent` file and `bundle-meta.xml` to:
```
force-app/main/default/aiAuthoringBundles/<AgentName>/
  <AgentName>.agent
  <AgentName>.bundle-meta.xml
```

The bundle-meta.xml MUST be minimal -- only `<bundleType>AGENT</bundleType>`. No extra fields.

See [references/syntax-reference.md](references/syntax-reference.md) for the complete Agent Script DSL syntax.
See [references/examples.md](references/examples.md) for complete agent examples.

### Phase 3b: Post-Generation Check -- Action Invocation Verification

**CRITICAL:** After generating, verify ALL topics with actions have instructions that
explicitly reference those actions. The LLM treats vague instructions as optional.

**Check 1 -- setVariables Sequential Collection:**
If any topic uses `@utils.setVariables` with `available when` guards, instructions MUST
use literal mode (`|`) with explicit action-invocation directives:
```
instructions: |
	Step 1: Use set_first_name to capture the customer's first name.
	Step 2: Use set_last_name to capture the customer's last name.
	CRITICAL: Always invoke the setVariables action to save data.
```
Do NOT use procedural mode (`->`) with passive phrasing -- the LLM won't call the action.

**Check 2 -- Backend Action Topics:**
Instructions must reference actions by purpose, not just describe the goal.

**Check 3 -- Anti-Hallucination:**
Every topic with backend actions must discourage fabricating data.

**Check 4 -- Set Clause Output Completeness:**
Trace data flow from each `set` clause to where the variable is consumed.

**Check 5 -- Action Chain Variable Capture:**
Topics chaining 3+ actions must capture intermediate results in variables.

**Check 6 -- Instruction mode consistency:**
Procedural `->` requires ALL content inside `if`/`else` blocks. No bare `|` after if blocks.

### Phase 4: Validate

```bash
sf agent validate authoring-bundle --api-name <AgentName> -o <org> --json
```

Before running, manually verify:
- Every `@actions.X` in reasoning has a matching Level 1 definition
- Every Level 1 action has `target:`, `inputs:`, `outputs:`
- Tab indentation throughout

### Phase 5: Review

Run safety review against the generated file. Include findings in the 100-point score.
See [references/scoring-rubric.md](references/scoring-rubric.md) for the rubric.

### Phase 6: Preview & Test

Run a live preview session with `--authoring-bundle` to generate trace files:
```bash
SESSION_ID=$(sf agent preview start --authoring-bundle <AgentName> --target-org <org> --json 2>/dev/null | jq -r '.result.sessionId')

sf agent preview send --session-id "$SESSION_ID" --authoring-bundle <AgentName> --utterance "$UTT" --target-org <org> --json

sf agent preview end --session-id "$SESSION_ID" --authoring-bundle <AgentName> --target-org <org> --json
```

**Trace files:** `.sfdx/agents/<AgentName>/sessions/<sessionId>/traces/<planId>.json`

**Fix loop (max 3 iterations):** If trace analysis reveals issues, edit the `.agent` file and re-preview.

| Trace symptom | Fix |
|---------------|-----|
| Wrong topic in `.topic` | Add keywords to topic description |
| Action missing from tools | Relax `available when` guard |
| `"category": "UNGROUNDED"` | Add variable references to instructions |
| `topic: "DefaultTopic"` | Add keywords to descriptions |

### Phase 6b: Review & Iterate

Present results to user. **Do NOT auto-proceed to deployment.** Ask what they want to do.

### Phase 7: Deploy

Once the user explicitly approves:

1. **Check targets exist** -- verify flow/apex targets are in the org
2. **Scaffold if needed** -- generate stubs for missing targets
3. **Publish and activate:**
```bash
sf agent publish authoring-bundle --api-name <AgentName> -o <org> --json
sf agent activate --api-name <AgentName> -o <org>
```

See [references/deploy-reference.md](references/deploy-reference.md) for the full deployment lifecycle.

---

## 3. SYNTAX QUICK REFERENCE

The complete Agent Script syntax is in [references/syntax-reference.md](references/syntax-reference.md). Key points:

**Block order:** `config:` > `variables:` > `system:` > `connection messaging:` > `knowledge:` > `language:` > `start_agent topic_selector:` > `topic:`

**Indentation:** Tabs only. Server rejects spaces.

**Two-level action system:**
- Level 1 (topic > actions): Defines WHAT -- `target:`, `inputs:`, `outputs:`
- Level 2 (reasoning > actions): Defines HOW -- `with`/`set` bindings, `available when`

**Critical rules:**
- `developer_name` must match folder name exactly
- Do NOT include `agent_type` in the file (server crash)
- `start_agent` must say "You are a router only. Do NOT answer directly."
- Booleans: `True`/`False` (capitalized)
- Strings: always double-quoted
- Numeric action I/O: use `object` + `complex_data_type_name` (not bare `number`)
- `after_reasoning:` has NO `instructions:` wrapper
- No `else if` -- use compound `if x and y:` or sequential flat ifs
- Reserved names: `description`, `label`, `language`, `escalate` -- cannot be used as variable/field names

See [references/syntax-reference.md](references/syntax-reference.md) for the full constraints table.

---

## 4. ARCHITECTURE PATTERNS

Three primary patterns for agent FSM design. Full details with code in [references/architecture-patterns.md](references/architecture-patterns.md).

- **Hub-and-Spoke** (most common): `start_agent` routes to specialized topics. Each topic has "back to hub" transition. Do NOT create a separate routing topic.
- **Verification Gate**: Identity verification before protected topics. `available when` guards on protected transitions.
- **Post-Action Loop**: Post-action checks at TOP of `instructions: ->` trigger on re-resolution after action completes.

---

## 5. NAMING & GOTCHAS

Agent names: PascalCase. Topics/actions: snake_case. Variables: camelCase or snake_case (be consistent). Apex class names: max 40 chars.

See [references/naming-and-gotchas.md](references/naming-and-gotchas.md) for full naming conventions, deployment gotchas, credit consumption, and production tips.

---

## 6. SCORING RUBRIC

Score every generated agent on 100 points across 7 categories: Structure (15), Safety (15), Deterministic Logic (20), Instruction Resolution (20), FSM Architecture (10), Action Configuration (10), Deployment Readiness (10).

See [references/scoring-rubric.md](references/scoring-rubric.md) for the complete rubric.

---

## 7. REFERENCE DOC MAP

| Need | Reference |
|------|-----------|
| Complete Agent Script syntax + constraints | [references/syntax-reference.md](references/syntax-reference.md) |
| Scoring rubric (100-point) | [references/scoring-rubric.md](references/scoring-rubric.md) |
| Architecture patterns (hub-spoke, gate, loop) | [references/architecture-patterns.md](references/architecture-patterns.md) |
| Complete agent examples (minimal + multi-topic) | [references/examples.md](references/examples.md) |
| Target discovery (Section 16) | [references/discover-reference.md](references/discover-reference.md) |
| Stub scaffolding (Section 17) | [references/scaffold-reference.md](references/scaffold-reference.md) |
| Deployment lifecycle (Section 18) | [references/deploy-reference.md](references/deploy-reference.md) |
| Safety review (Section 15) | [references/safety-review-reference.md](references/safety-review-reference.md) |
| Naming conventions + gotchas | [references/naming-and-gotchas.md](references/naming-and-gotchas.md) |
| Agent Script to Lightning type mapping | [references/complex-data-types.md](references/complex-data-types.md) |
| Preview test loop | [references/preview-test-loop.md](references/preview-test-loop.md) |
| Action definitions, targets, I/O binding | [references/actions-reference.md](references/actions-reference.md) |
| How instructions resolve at runtime | [references/instruction-resolution.md](references/instruction-resolution.md) |
| Reading traces, jq recipes | [references/debugging-guide.md](references/debugging-guide.md) |
| Platform issues and workarounds | [references/known-issues.md](references/known-issues.md) |
| Credit consumption, lifecycle hooks, limits | [references/production-gotchas.md](references/production-gotchas.md) |
| Feature validity by context | [references/feature-validity.md](references/feature-validity.md) |

---

## 8. TEMPLATE ASSETS

Ready-to-use `.agent` templates. Copy and customize for new agents.

| Template | Description | File |
|----------|-------------|------|
| Hello World | Minimal single-topic agent | `assets/hello-world.agent` |
| Hub-and-Spoke | Central router with 3 spokes | `assets/hub-and-spoke.agent` |
| Multi-Topic | Hub-and-spoke with Flow actions | `assets/multi-topic.agent` |
| Order Service | Verification gate + order/tracking/returns | `assets/order-service.agent` |
| Verification Gate | Security gate with churn-risk refund logic | `assets/verification-gate.agent` |

See also [references/examples.md](references/examples.md) for inline code examples.

---

## 9. REVIEW MODE

When the user provides a path to an existing `.agent` file (e.g., `review path/to/file.agent`):

1. Read the file
2. Score it against the 100-point rubric
3. List every issue, grouped by category
4. Provide corrected code snippets
5. Offer to apply fixes via Edit tool

Common findings: missing linked variables, `developer_name` mismatch, missing `language:` block, dead-end topics, wrong instruction mode, uncapitalized booleans, missing safety disclosures.

---

## 10. SAFETY REVIEW

7-category LLM-driven safety review for `.agent` files. Integrated into Phases 0 and 5 of authoring, and Phase 0 of deployment. Can also be invoked on-demand.

See [references/safety-review-reference.md](references/safety-review-reference.md) for the complete review framework, categories, severity levels, false positive guidance, and adversarial test prompts.

---

## 11. DISCOVER

Validates that `.agent` file action targets exist in a Salesforce org. Provides fuzzy suggestions for missing targets and I/O parameter validation.

```bash
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-file <path>
```

See [references/discover-reference.md](references/discover-reference.md) for full usage, org validation queries, and CI/CD integration.

---

## 12. SCAFFOLD

Generates stub metadata (Flow XML, Apex classes + tests) for missing action targets. Supports action classification (callout, soql, basic) and SObject-aware generation.

```bash
python3 "$ADLC_SCRIPTS/scaffold.py" --agent-file <path> -o <org-alias> --output-dir force-app/main/default
```

**CRITICAL:** Stubs must return realistic data, not `'TODO'`. Placeholder responses cause SMALL_TALK grounding because the LLM falls back to training data.

See [references/scaffold-reference.md](references/scaffold-reference.md) for full usage, type mapping, stub data guidelines, and best practices.

---

## 13. DEPLOY

Full deployment lifecycle: validate > deploy metadata > publish bundle > activate.

```bash
sf agent publish authoring-bundle --api-name <AgentName> -o <org-alias> --json
sf agent activate --api-name <AgentName> -o <org-alias>
```

See [references/deploy-reference.md](references/deploy-reference.md) for phases, error recovery, CI/CD integration, and rollback procedures.

---

## 14. FEEDBACK

Collect structured feedback and submit via Google Form.

```bash
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''<feedback summary>'''))")
FORM_URL="https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=${ENCODED}"
open "$FORM_URL"
```

**Privacy:** Never include org IDs, session IDs, tokens, source code, or credentials.
**When:** Offer feedback once after any development phase completes. Do not repeat if ignored.
