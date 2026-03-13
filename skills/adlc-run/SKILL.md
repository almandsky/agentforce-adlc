---
name: adlc-run
description: Execute individual Agentforce actions against a live Salesforce org via REST API
allowed-tools: Bash Read Glob
argument-hint: "<org-alias> --target <flow://Name|apex://Class> [--inputs key=value,...]"
---

# ADLC Run

Execute individual Agentforce actions directly against a Salesforce org for testing and debugging.

## Overview

This skill enables direct invocation of Flow and Apex actions referenced in Agent Script files, bypassing the agent runtime. It's useful for testing action logic in isolation, debugging input/output mappings, and validating that actions work correctly before agent deployment.

## Script Path

The scripts live inside the installed repo copy. Resolve the path based on which IDE config directory exists:

```bash
# macOS / Linux
ADLC_SCRIPTS="$([ -d ~/.claude/adlc ] && echo ~/.claude/adlc/scripts || echo ~/.cursor/adlc/scripts)"
```

```powershell
# Windows (PowerShell)
$ADLC_SCRIPTS = if (Test-Path "$env:USERPROFILE\.claude\adlc") { "$env:USERPROFILE\.claude\adlc\scripts" } else { "$env:USERPROFILE\.cursor\adlc\scripts" }
```

**Note:** Use `python` instead of `python3` on Windows.

## Usage

```bash
# Execute a Flow action
python3 "$ADLC_SCRIPTS/run.py" \
  -o <org-alias> \
  --target "flow://Get_Order_Status" \
  --inputs "orderId=00190000023XXXX"

# Execute an Apex action with multiple inputs
python3 "$ADLC_SCRIPTS/run.py" \
  -o <org-alias> \
  --target "apex://OrderProcessor" \
  --inputs "orderId=00190000023XXXX,actionType=cancel,reason=Customer request"

# Execute with JSON input for complex data
python3 "$ADLC_SCRIPTS/run.py" \
  -o <org-alias> \
  --target "flow://Process_Return" \
  --input-file inputs.json

# Test mode (show request without executing)
python3 "$ADLC_SCRIPTS/run.py" \
  -o <org-alias> \
  --target "apex://CustomerService" \
  --inputs "customerId=001XX000003DHXX" \
  --test
```

## Target Protocols

### Flow Actions (`flow://`)

Executes an Autolaunched Flow via REST API:

```
POST /services/data/v66.0/actions/custom/flow/{flowApiName}
```

Example request body:
```json
{
  "inputs": [
    {
      "orderId": "00190000023XXXX",
      "includeDetails": true
    }
  ]
}
```

Example response:
```json
{
  "actionName": "Get_Order_Status",
  "errors": [],
  "isSuccess": true,
  "outputValues": {
    "orderStatus": "Shipped",
    "trackingNumber": "1Z999AA10123456784",
    "estimatedDelivery": "2024-03-15"
  }
}
```

### Apex Actions (`apex://`)

Executes an @InvocableMethod via REST API:

```
POST /services/data/v66.0/actions/custom/apex/{className}
```

The Apex class must have exactly one method annotated with `@InvocableMethod`.

Example request body:
```json
{
  "inputs": [
    {
      "orderId": "00190000023XXXX",
      "actionType": "cancel"
    }
  ]
}
```

Example response:
```json
{
  "actionName": "OrderProcessor",
  "errors": [],
  "isSuccess": true,
  "outputValues": [
    {
      "success": true,
      "message": "Order cancelled successfully",
      "refundAmount": 299.99
    }
  ]
}
```

## Input Formats

### Key-Value Pairs

Simple inputs via command line:
```bash
--inputs "key1=value1,key2=value2,key3=value3"
```

Type inference:
- Numbers: `amount=299.99` → `299.99` (numeric)
- Booleans: `isUrgent=true` → `true` (boolean)
- Strings: `status=Active` → `"Active"` (string)
- IDs: Detected by pattern → `"001XX000003DHXX"` (string)

### JSON File

Complex inputs via file:
```json
{
  "orderId": "00190000023XXXX",
  "lineItems": [
    {
      "productId": "01tXX0000008cXX",
      "quantity": 2,
      "discount": 0.1
    }
  ],
  "shippingAddress": {
    "street": "123 Main St",
    "city": "San Francisco",
    "state": "CA",
    "postalCode": "94105"
  }
}
```

Usage:
```bash
--input-file order-inputs.json
```

### Environment Variables

Sensitive data via environment:
```bash
export ORDER_ID="00190000023XXXX"
export API_KEY="secret-key-123"

python3 scripts/run.py -o myorg \
  --target "flow://Process_Order" \
  --inputs "orderId=$ORDER_ID,apiKey=$API_KEY"
```

## Output Handling

### Standard Output

Default format shows key information:
```
Executing: flow://Get_Order_Status
Org: myorg
Inputs: {"orderId": "00190000023XXXX"}

Response:
✓ Success
Outputs:
  - orderStatus: Shipped
  - trackingNumber: 1Z999AA10123456784
  - estimatedDelivery: 2024-03-15
```

### JSON Output

For programmatic processing:
```bash
python3 scripts/run.py -o myorg \
  --target "flow://Get_Order_Status" \
  --inputs "orderId=001XX" \
  --json
```

Output:
```json
{
  "success": true,
  "actionName": "Get_Order_Status",
  "outputs": {
    "orderStatus": "Shipped",
    "trackingNumber": "1Z999AA10123456784"
  },
  "executionTime": 1245,
  "apiVersion": "66.0"
}
```

### Error Output

When action fails:
```json
{
  "success": false,
  "actionName": "Process_Order",
  "errors": [
    {
      "statusCode": "FIELD_CUSTOM_VALIDATION_EXCEPTION",
      "message": "Order amount exceeds credit limit",
      "fields": ["CreditLimit__c"]
    }
  ],
  "executionTime": 890
}
```

## Authentication

The script uses Salesforce CLI authentication:

```bash
# Ensure org is authenticated
sf org display -o <org-alias>

# If not authenticated, login first
sf org login web --alias <org-alias>
```

The script automatically:
1. Retrieves access token from CLI
2. Determines instance URL
3. Constructs proper REST endpoint
4. Adds required headers

## Debugging Features

### Test Mode

Preview request without execution:
```bash
python3 scripts/run.py -o myorg \
  --target "flow://Complex_Flow" \
  --inputs "id=001XX" \
  --test
```

Output:
```
TEST MODE - Would execute:
URL: https://myorg.my.salesforce.com/services/data/v66.0/actions/custom/flow/Complex_Flow
Headers:
  Authorization: Bearer [TOKEN]
  Content-Type: application/json
Body:
{
  "inputs": [{"id": "001XX"}]
}
```

### Verbose Mode

Show detailed request/response:
```bash
python3 scripts/run.py -o myorg \
  --target "apex://MyClass" \
  --inputs "id=001XX" \
  --verbose
```

Shows:
- Full HTTP request headers
- Complete request body
- Raw response headers
- Full response body
- Timing information

### Debug Logging

Enable Apex debug logs:
```bash
# Set up debug logging for the user
sf data create record -s DebugLevel \
  -v "DeveloperName=ADLC_Debug MasterLabel=ADLC_Debug ApexCode=FINEST Workflow=FINER" \
  -o <org>

# Run action with debug flag
python3 scripts/run.py -o myorg \
  --target "apex://MyClass" \
  --inputs "id=001XX" \
  --debug

# Retrieve debug log
sf apex log get --number 1 -o <org>
```

## Integration Testing

### Test Flow Pattern

1. **Prepare test data**:
```bash
# Create test record
RECORD_ID=$(sf data create record -s Account \
  -v "Name='Test Account' Type='Customer'" \
  -o myorg --json | jq -r '.result.id')
```

2. **Execute action**:
```bash
python3 scripts/run.py -o myorg \
  --target "flow://Update_Account" \
  --inputs "accountId=$RECORD_ID,status=Active"
```

3. **Verify results**:
```bash
# Query updated record
sf data query \
  --query "SELECT Name, Status__c FROM Account WHERE Id = '$RECORD_ID'" \
  -o myorg --json
```

4. **Clean up**:
```bash
sf data delete record -s Account -i $RECORD_ID -o myorg
```

### Batch Testing

Test multiple inputs from CSV:

```python
#!/usr/bin/env python3
import csv
import subprocess
import json

with open('test-inputs.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        inputs = ','.join([f"{k}={v}" for k,v in row.items()])
        cmd = f"python3 scripts/run.py -o myorg --target 'flow://MyFlow' --inputs '{inputs}' --json"
        result = subprocess.run(cmd, shell=True, capture_output=True)
        data = json.loads(result.stdout)
        print(f"{row['testId']}: {'✓' if data['success'] else '✗'}")
```

## Performance Monitoring

The script tracks execution time:

```bash
python3 scripts/run.py -o myorg \
  --target "apex://SlowProcess" \
  --inputs "size=1000" \
  --json | jq '.executionTime'
```

For performance testing:
```bash
# Run 10 iterations and measure
for i in {1..10}; do
  python3 scripts/run.py -o myorg \
    --target "flow://MyFlow" \
    --inputs "iteration=$i" \
    --json | jq '.executionTime'
done | awk '{sum+=$1} END {print "Avg:", sum/NR, "ms"}'
```

## Error Handling

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `NOT_FOUND` | Flow/Apex not found | Verify target name and deployment |
| `INVALID_INPUT` | Input parameter mismatch | Check required inputs in Flow/Apex |
| `INSUFFICIENT_ACCESS` | Permission issue | Verify user permissions |
| `LIMIT_EXCEEDED` | Governor limit hit | Reduce batch size or optimize logic |
| `INVALID_SESSION_ID` | Auth expired | Re-authenticate: `sf org login web` |

### Retry Logic

The script includes automatic retry for transient failures:

```python
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

for attempt in range(MAX_RETRIES):
    try:
        response = execute_action(target, inputs)
        if response.status_code == 200:
            break
    except RequestException:
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
            continue
        raise
```

## Best Practices

### Input Validation

Always validate inputs before execution:
- Check required fields are present
- Verify ID format (15 or 18 characters)
- Validate data types match expected
- Sanitize user input to prevent injection

### Output Verification

After execution:
- Check `isSuccess` flag
- Verify expected outputs are present
- Validate output data types
- Check for partial success scenarios

### Error Recovery

Implement proper error handling:
- Log all failures with context
- Implement compensating transactions
- Alert on critical failures
- Maintain audit trail

## Script Location

The run script should be located at:
```
$ADLC_SCRIPTS/run.py
```
(see Script Path section above)

Required dependencies:
- `requests` - HTTP client for REST API
- `simple-salesforce` - Salesforce authentication
- `python-dotenv` - Environment variable support
- `colorama` - Terminal output formatting

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | Action executed successfully |
| 1 | Action failed | Business logic error or validation failure |
| 2 | Connection error | Network or authentication issue |
| 3 | Invalid input | Malformed input or missing required fields |

---

## Feedback

If the user encounters unexpected errors or the action execution didn't behave as expected:

```
If the action results weren't what you expected, run /adlc-feedback to let us know —
it helps improve the run skill.
```

Only mention feedback once per session. Do not repeat if the user ignores it.