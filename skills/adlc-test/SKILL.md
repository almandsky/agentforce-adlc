---
name: adlc-test
description: Smoke test Agentforce agents using sf agent preview and batch testing
allowed-tools: Bash Read Write Edit Glob Grep
argument-hint: "<org-alias> --api-name <AgentName> [--utterances <file>]"
---

# ADLC Test

Automated testing for Agentforce agents with smoke tests, batch execution, and iterative fix loops.

## Overview

This skill provides comprehensive testing capabilities for Agentforce agents, including automated utterance derivation from agent topics, preview-based smoke testing, trace analysis, and an iterative fix loop for identified issues. It bridges the gap between initial development and production deployment.

## Usage

```bash
# Basic smoke test with derived utterances
python3 /Users/sky.chen/Documents/projects/agentforce-adlc/scripts/test.py \
  -o <org-alias> \
  --api-name MyAgent

# Test with custom utterances file
python3 /Users/sky.chen/Documents/projects/agentforce-adlc/scripts/test.py \
  -o <org-alias> \
  --api-name MyAgent \
  --utterances test-cases.txt

# Test authoring bundle (pre-publish)
python3 /Users/sky.chen/Documents/projects/agentforce-adlc/scripts/test.py \
  -o <org-alias> \
  --api-name MyAgent \
  --authoring-bundle

# Verbose mode with trace saving
python3 /Users/sky.chen/Documents/projects/agentforce-adlc/scripts/test.py \
  -o <org-alias> \
  --api-name MyAgent \
  --save-traces \
  --verbose
```

## Testing Workflow

### Phase 1: Utterance Derivation

If no utterances file is provided, the system automatically derives test cases from the `.agent` file:

1. **Topic-based utterances** - One per non-start topic based on description keywords
2. **Action-based utterances** - Target each key action's functionality
3. **Guardrail test** - Off-topic utterance to test boundaries
4. **Multi-turn scenarios** - Test topic transitions if defined

Example derivation from agent structure:
```yaml
# Agent topics:
topic order_management:
  description: "Handle order status, tracking, shipping"
  actions:
    - get_order_status
    - track_shipment

topic returns:
  description: "Process returns, refunds, exchanges"
  actions:
    - initiate_return
    - check_refund_status

# Derived utterances:
1. "Where is my order?" → should route to order_management
2. "I want to return this item" → should route to returns
3. "Track my shipment" → should invoke track_shipment action
4. "What's my refund status?" → should invoke check_refund_status
5. "Tell me a joke" → should trigger guardrail
6. "Check my order" + "Actually, I want to return it" → test transition
```

### Phase 2: Preview Execution

Execute tests using `sf agent preview` programmatically:

```bash
# Start preview session
SESSION_ID=$(sf agent preview start \
  --api-name MyAgent \
  --target-org <org> --json 2>/dev/null \
  | jq -r '.result.sessionId')

# Send each test utterance
for UTTERANCE in "${TEST_UTTERANCES[@]}"; do
  RESPONSE=$(sf agent preview send \
    --session-id "$SESSION_ID" \
    --api-name MyAgent \
    --utterance "$UTTERANCE" \
    --target-org <org> --json 2>/dev/null)

  # Capture plan ID for trace analysis
  PLAN_ID=$(echo "$RESPONSE" | jq -r '.result.messages[-1].planId')
  PLAN_IDS+=("$PLAN_ID")
done

# End session and get traces
TRACES_PATH=$(sf agent preview end \
  --session-id "$SESSION_ID" \
  --target-org <org> --json 2>/dev/null \
  | jq -r '.result.tracesPath')
```

### Phase 3: Trace Analysis

Analyze execution traces for 6 key aspects:

#### 1. Topic Routing Verification
```bash
jq '[.steps[] | select(.stepType == "TransitionStep") | .data.to]' "$TRACE"
```
Expected: Correct topic name in array

#### 2. Action Invocation Check
```bash
jq '[.steps[] | select(.stepType == "FunctionStep") | .data.function]' "$TRACE"
```
Expected: Target action name present

#### 3. Grounding Assessment
```bash
jq '[.steps[] | select(.stepType == "ReasoningStep") | .data.groundingAssessment]' "$TRACE"
```
Expected: "GROUNDED" (not "UNGROUNDED")

#### 4. Safety Score Validation
```bash
jq '.steps[] | select(.stepType == "PlannerResponseStep") | .data.safetyScore.overall' "$TRACE"
```
Expected: >= 0.9

#### 5. Tool Visibility
```bash
jq '[.steps[] | select(.stepType == "EnabledToolsStep") | .data.enabled_tools]' "$TRACE"
```
Expected: Required actions present in array

#### 6. Response Quality
```bash
jq '.steps[] | select(.stepType == "PlannerResponseStep") | .data.responseText' "$TRACE"
```
Expected: Relevant, coherent response

### Phase 4: Fix Loop

If issues are detected, the system enters an automated fix loop (max 3 iterations):

#### Iteration Process

1. **Identify failure category**:
   - `TOPIC_NOT_MATCHED` - Topic description too vague
   - `ACTION_NOT_INVOKED` - Action guard too restrictive
   - `WRONG_ACTION_SELECTED` - Action descriptions overlap
   - `UNGROUNDED_RESPONSE` - Missing data references
   - `LOW_SAFETY_SCORE` - Inadequate safety instructions
   - `TOOL_NOT_VISIBLE` - Available when conditions not met

2. **Apply targeted fix**:

| Failure Type | Fix Location | Fix Strategy |
|--------------|--------------|--------------|
| TOPIC_NOT_MATCHED | `topic: description:` | Add keywords from utterance |
| ACTION_NOT_INVOKED | `available when:` | Relax guard conditions |
| WRONG_ACTION | Action descriptions | Add exclusion language |
| UNGROUNDED | `instructions: ->` | Add `{!@variables.x}` references |
| LOW_SAFETY | `system: instructions:` | Add safety guidelines |

3. **Validate fix** - LSP auto-validates on save

4. **Re-test** - New preview session with failing utterance

5. **Evaluate** - Check if issue resolved, continue or exit loop

Example fix application:
```yaml
# Before (topic not matched)
topic order_mgmt:
  description: "Orders"

# After (expanded description)
topic order_mgmt:
  description: "Handle order queries, order status, tracking, shipping, delivery"
```

## Test Report Format

### Summary Report
```
Agentforce Agent Test Report
═══════════════════════════════════════════

Agent: OrderManagementAgent
Org: production
Test Cases: 6
Duration: 45.2s

Results:
✓ Topic Routing: 5/6 passed (83.3%)
✓ Action Invocation: 4/6 passed (66.7%)
✓ Grounding: 6/6 passed (100%)
✓ Safety: 6/6 passed (100%)
⚠ Response Quality: 5/6 passed (83.3%)

Overall Score: 86.7%
Status: PASSED WITH WARNINGS
```

### Detailed Test Cases
```
Test Case 1: "Where is my order?"
├─ Expected Topic: order_mgmt
├─ Actual Topic: order_mgmt ✓
├─ Expected Action: get_order_status
├─ Actual Action: get_order_status ✓
├─ Grounding: GROUNDED ✓
├─ Safety Score: 0.95 ✓
└─ Response Quality: Relevant ✓

Test Case 2: "I want to return this"
├─ Expected Topic: returns
├─ Actual Topic: order_mgmt ✗ (misrouted)
├─ Fix Applied: Expanded 'returns' topic description
└─ Retry Result: Correctly routed ✓
```

## Batch Testing

### Test Definition File

Create a YAML file with test cases:

```yaml
# test-cases.yaml
test_suite:
  name: "Order Management Tests"
  agent: "OrderManagementAgent"

test_cases:
  - id: "TC001"
    utterance: "Where is my order #12345?"
    expected_topic: "order_mgmt"
    expected_action: "get_order_status"

  - id: "TC002"
    utterance: "I want to return my purchase"
    expected_topic: "returns"
    expected_action: "initiate_return"

  - id: "TC003"
    utterances:  # Multi-turn test
      - "Check order status"
      - "Actually, cancel it instead"
    expected_topics: ["order_mgmt", "order_mgmt"]
    expected_actions: ["get_order_status", "cancel_order"]
```

### Execution

```bash
python3 scripts/test.py \
  -o myorg \
  --api-name OrderManagementAgent \
  --test-suite test-cases.yaml \
  --parallel 3  # Run 3 sessions in parallel
```

## Performance Metrics

The test framework captures performance data:

| Metric | Description | Threshold |
|--------|-------------|-----------|
| Topic routing time | Time to select topic | < 2000ms |
| Action execution time | Time for action to complete | < 5000ms |
| Total turn time | End-to-end response time | < 8000ms |
| Token usage | LLM tokens consumed | < 2000/turn |

Performance report:
```
Performance Analysis
────────────────────
Average topic routing: 1245ms
Average action time: 3421ms
Average turn time: 5892ms
P95 turn time: 7234ms
Total tokens used: 8456
Estimated cost: $0.42
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Agent Testing
on:
  pull_request:
    paths:
      - 'force-app/**/*.agent'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          npm install -g @salesforce/cli

      - name: Authenticate org
        run: |
          echo "${{ secrets.SFDX_AUTH_URL }}" > auth.txt
          sf org login sfdx-url --sfdx-url-file auth.txt --alias testorg

      - name: Run agent tests
        run: |
          python3 scripts/test.py \
            -o testorg \
            --api-name ${{ vars.AGENT_NAME }} \
            --save-traces \
            --junit-output test-results.xml

      - name: Upload test results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: |
            test-results.xml
            traces/
```

## Advanced Features

### Custom Assertions

Define custom test assertions:

```python
# custom_assertions.py
def assert_contains_order_number(response):
    """Verify response contains an order number"""
    import re
    pattern = r'#\d{5,10}'
    assert re.search(pattern, response), "No order number in response"

def assert_polite_tone(response):
    """Check for polite language"""
    polite_phrases = ['please', 'thank you', 'happy to help']
    assert any(phrase in response.lower() for phrase in polite_phrases)
```

### Test Data Management

Prepare test data before execution:

```bash
# Setup test data
sf data create record -s Account \
  -v "Name='Test Customer' Email__c='test@example.com'" \
  -o testorg --json > test-account.json

ACCOUNT_ID=$(jq -r '.result.id' test-account.json)

# Run tests with context
python3 scripts/test.py \
  -o testorg \
  --api-name MyAgent \
  --context "accountId=$ACCOUNT_ID"

# Cleanup
sf data delete record -s Account -i $ACCOUNT_ID -o testorg
```

### Coverage Analysis

Track which topics and actions are tested:

```
Coverage Report
───────────────
Topics Tested: 4/5 (80%)
  ✓ order_mgmt
  ✓ returns
  ✓ shipping
  ✓ support
  ✗ admin (not tested)

Actions Tested: 8/12 (66.7%)
  ✓ get_order_status
  ✓ track_shipment
  ✓ initiate_return
  ✓ check_refund
  ✗ escalate_to_human
  ✗ schedule_callback
  ...

Recommendations:
- Add test for 'admin' topic
- Test escalation scenarios
- Add negative test cases
```

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Session timeout | Long-running tests | Split into smaller batches |
| Trace not found | CLI version issue | Update to sf CLI 2.121.7+ |
| Action mock fails | Complex inputs | Use `--use-live-actions` flag |
| Context variables missing | Preview limitation | Use Runtime API for context tests |

### Debug Mode

Enable detailed logging:

```bash
# Set debug environment variables
export ADLC_DEBUG=true
export ADLC_LOG_LEVEL=DEBUG

# Run with debug output
python3 scripts/test.py \
  -o myorg \
  --api-name MyAgent \
  --debug \
  --verbose
```

## Best Practices

### Test Strategy

1. **Start with smoke tests** - Basic happy path scenarios
2. **Add edge cases** - Boundary conditions, invalid inputs
3. **Test transitions** - Multi-turn conversations
4. **Verify guardrails** - Off-topic and safety boundaries
5. **Performance baseline** - Establish acceptable response times

### Test Maintenance

- Version test cases with agent versions
- Update expected outputs when agent evolves
- Archive historical test results
- Monitor test flakiness and address root causes

## Script Location

Test script location:
```
/Users/sky.chen/Documents/projects/agentforce-adlc/scripts/test.py
```

Required dependencies:
- `pyyaml` - Parse test definitions
- `jq` (system) - JSON processing
- `colorama` - Terminal colors
- `junit-xml` - JUnit report generation

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | All tests passed | Safe to deploy |
| 1 | Some tests failed | Review failures before deploying |
| 2 | Critical test failure | Block deployment |
| 3 | Test execution error | Fix test infrastructure |