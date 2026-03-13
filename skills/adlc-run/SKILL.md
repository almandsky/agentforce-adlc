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

## Usage

### Setup: Get Org Credentials

```bash
# Ensure org is authenticated
sf org display -o <org-alias>

# If not authenticated, login first
sf org login web --alias <org-alias>

# Extract credentials for API calls
TOKEN=$(sf org display -o <org-alias> --json | jq -r '.result.accessToken')
INSTANCE_URL=$(sf org display -o <org-alias> --json | jq -r '.result.instanceUrl')
```

### Execute a Flow Action

```bash
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow/Get_Order_Status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": [{"orderId": "00190000023XXXX"}]}'
```

### Execute an Apex Action

```bash
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/apex/OrderProcessor" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": [{"orderId": "00190000023XXXX", "actionType": "cancel", "reason": "Customer request"}]}'
```

### Execute with JSON Input File

For complex inputs, write a JSON file and pass it to curl:

```bash
cat > /tmp/action-inputs.json << 'EOF'
{
  "inputs": [
    {
      "orderId": "00190000023XXXX",
      "lineItems": [
        {"productId": "01tXX0000008cXX", "quantity": 2, "discount": 0.1}
      ]
    }
  ]
}
EOF

curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow/Process_Return" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/action-inputs.json
```

### Pretty-Print Response

Pipe through `jq` for readable output:

```bash
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow/Get_Order_Status" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": [{"orderId": "00190000023XXXX"}]}' | jq .
```

## Target Protocols

### Flow Actions (`flow://`)

Executes an Autolaunched Flow via REST API:

```
POST /services/data/v63.0/actions/custom/flow/{flowApiName}
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
POST /services/data/v63.0/actions/custom/apex/{className}
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

## Integration Testing

### Test Flow Pattern

1. **Prepare test data**:
```bash
RECORD_ID=$(sf data create record -s Account \
  -v "Name='Test Account' Type='Customer'" \
  -o myorg --json | jq -r '.result.id')
```

2. **Execute action**:
```bash
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow/Update_Account" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"inputs\": [{\"accountId\": \"$RECORD_ID\", \"status\": \"Active\"}]}" | jq .
```

3. **Verify results**:
```bash
sf data query \
  --query "SELECT Name, Status__c FROM Account WHERE Id = '$RECORD_ID'" \
  -o myorg --json
```

4. **Clean up**:
```bash
sf data delete record -s Account -i $RECORD_ID -o myorg
```

## Debugging

### Retrieve Apex Debug Logs

After executing an Apex action, fetch the most recent debug log:

```bash
sf apex log get --number 1 -o <org-alias>
```

### Inspect Available Actions

List all available custom actions to verify deployment:

```bash
# List all Flow actions
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/flow" \
  -H "Authorization: Bearer $TOKEN" | jq '.actions[].name'

# List all Apex actions
curl -s "$INSTANCE_URL/services/data/v63.0/actions/custom/apex" \
  -H "Authorization: Bearer $TOKEN" | jq '.actions[].name'
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

### Best Practices

- Check `isSuccess` in the response before processing outputs
- Verify ID format (15 or 18 characters) before sending
- Use `jq` to extract specific fields from responses
- Create and clean up test data to avoid polluting the org

---

## Feedback

If the user encounters unexpected errors or the action execution didn't behave as expected:

```
If the action results weren't what you expected, run /adlc-feedback to let us know --
it helps improve the run skill.
```

Only mention feedback once per session. Do not repeat if the user ignores it.
