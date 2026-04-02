# Discover -- Target Discovery Reference

> Extracted from SKILL.md Section 16. This file is loaded on demand when target discovery details are needed.

## Overview

Validates that Agent Script `.agent` file targets actually exist in a Salesforce org, providing fuzzy suggestions for missing targets.

## Usage

```bash
# Discover targets for a specific .agent file
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-file force-app/main/default/aiAuthoringBundles/MyAgent/MyAgent.agent

# Discover targets for all .agent files in a directory
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-dir force-app/main/default/aiAuthoringBundles

# Include I/O parameter validation for found targets
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-file MyAgent.agent --validate-io
```

## What it does

### 1. Target Extraction
- Finds all `.agent` files in the project
- Parses each file to extract action `target:` values
- Identifies target types: `flow://`, `apex://`, `retriever://`, `externalService://`, `generatePromptResponse://`

### 2. Org Validation

| Target Type | SOQL Query | Object Checked |
|-------------|------------|----------------|
| `flow://FlowName` | `SELECT ApiName FROM FlowDefinitionView WHERE ApiName = 'FlowName' AND IsActive = true` | Active flows only |
| `apex://ClassName` | `SELECT Name FROM ApexClass WHERE Name = 'ClassName'` | Apex classes |
| `retriever://RetrieverName` | `SELECT DeveloperName FROM DataKnowledgeSpace WHERE DeveloperName = 'RetrieverName'` | Data Cloud retrievers |
| `externalService://ServiceName` | `SELECT DeveloperName FROM ExternalServiceRegistration WHERE DeveloperName = 'ServiceName'` | External services |
| `generatePromptResponse://TemplateName` | `SELECT DeveloperName FROM PromptTemplate WHERE DeveloperName = 'TemplateName' AND Status = 'Active'` | Active prompt templates |

### 3. Fuzzy Matching
When a target is missing:
- Queries for similar names using SOQL `LIKE` patterns
- Calculates Levenshtein distance for close matches
- Suggests up to 3 alternatives sorted by similarity

### 4. I/O Parameter Validation (--validate-io)
- **Flows:** Queries `/services/data/v63.0/actions/custom/flow/{FlowApiName}` for actual I/O schema
- **Apex:** Checks `@InvocableVariable` field names match expected inputs/outputs
- Results appear as non-blocking warnings

### 5. Classification for Scaffold Pipeline

| Signal in Description | Classification | Scaffold Output |
|----------------------|---------------|-----------------|
| "API", "HTTP", "REST", "external", URL | `callout` | Apex with Http + Remote Site + Custom Metadata |
| SObject names, "query", "record", "SOQL" | `soql` | Apex with SOQL query logic |
| No special signals | `basic` | Standard placeholder Apex |

## Output Format

```
Agentforce ADLC Discovery Report

Agent: OrderManagement
  Topic: order_inquiry
    Action: get_order_status
      Target: flow://Get_Order_Status         Found
    Action: track_shipment
      Target: flow://Track_Shipment_Flow      MISSING
        Suggestions:
          - Track_Shipping_Flow (distance: 2)

Summary: 2/3 targets found (66.7%)
```

## Next Steps

- Missing targets: Run scaffold (`python3 "$ADLC_SCRIPTS/scaffold.py" -o <org-alias> --agent-file <path>`)
- All found: Deploy (`sf agent publish authoring-bundle --api-name <AgentName> -o <org-alias>`)

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `No .agent files found` | Wrong directory | Check `--agent-file` path |
| `Invalid org alias` | Org not authenticated | Run `sf org login web --alias <org-alias>` |
| `SOQL query failed` | Missing permissions | Ensure read access to Flow, ApexClass, etc. |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All targets found |
| 1 | Some targets missing |
| 2 | Critical failure |
