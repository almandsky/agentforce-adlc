---
name: adlc-discover
description: Check which .agent file targets (flows, apex classes, retrievers) exist in a Salesforce org
allowed-tools: Bash Read Glob Grep
argument-hint: "<org-alias> [--agent-file <path>]"
---

# ADLC Discover

Validate that Agent Script `.agent` file targets actually exist in a Salesforce org, providing fuzzy suggestions for missing targets.

## Overview

This skill analyzes `.agent` files to extract action targets (`flow://`, `apex://`, `retriever://`, `externalService://`, `generatePromptResponse://`) and validates their existence in the target Salesforce org. It provides detailed reports including fuzzy matching suggestions when targets are missing.

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
# Discover targets for a specific .agent file
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-file force-app/main/default/aiAuthoringBundles/MyAgent/MyAgent.agent

# Discover targets for all .agent files in a directory
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-dir force-app/main/default/aiAuthoringBundles

# Include I/O parameter validation for found targets
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-file MyAgent.agent --validate-io
```

## What it does

### 1. Target Extraction
- Finds all `.agent` files in the project (default: `force-app/main/default/aiAuthoringBundles/`)
- Parses each file to extract action `target:` values
- Identifies target types: `flow://`, `apex://`, `retriever://`, `externalService://`, `generatePromptResponse://`
- Maintains mapping of which topic contains which action

### 2. Org Validation
For each extracted target, queries the Salesforce org:

| Target Type | SOQL Query | Object Checked |
|-------------|------------|----------------|
| `flow://FlowName` | `SELECT ApiName FROM FlowDefinitionView WHERE ApiName = 'FlowName' AND IsActive = true` | Active flows only |
| `apex://ClassName` | `SELECT Name FROM ApexClass WHERE Name = 'ClassName'` | Apex classes |
| `retriever://RetrieverName` | `SELECT DeveloperName FROM DataKnowledgeSpace WHERE DeveloperName = 'RetrieverName'` | Data Cloud retrievers |
| `externalService://ServiceName` | `SELECT DeveloperName FROM ExternalServiceRegistration WHERE DeveloperName = 'ServiceName'` | External services |
| `generatePromptResponse://TemplateName` | `SELECT DeveloperName FROM PromptTemplate WHERE DeveloperName = 'TemplateName' AND Status = 'Active'` | Active prompt templates |

### 3. Fuzzy Matching
When a target is missing, the skill:
- Queries for similar names using SOQL `LIKE` patterns
- Calculates Levenshtein distance for close matches
- Suggests up to 3 alternatives sorted by similarity

Example fuzzy suggestions:
```
Target: flow://Get_Order_Sttus (MISSING)
  Suggestions:
    - Get_Order_Status (distance: 1)
    - Get_Order_Details (distance: 7)
    - Get_Customer_Orders (distance: 9)
```

### 4. Report Generation

Outputs a comprehensive table with columns:
- **Agent**: Name of the `.agent` file
- **Topic**: Topic containing the action
- **Action**: Action name in the agent script
- **Target**: Full target URI (e.g., `flow://MyFlow`)
- **Status**: `✓ Found` or `✗ MISSING`
- **Suggestions**: Fuzzy matches if missing

## Output Format

```
Agentforce ADLC Discovery Report
═══════════════════════════════════════════════════════════════════════════

Agent: OrderManagement
├─ Topic: order_inquiry
│  ├─ Action: get_order_status
│  │  └─ Target: flow://Get_Order_Status         ✓ Found
│  └─ Action: track_shipment
│     └─ Target: flow://Track_Shipment_Flow      ✗ MISSING
│        Suggestions:
│          - Track_Shipping_Flow (distance: 2)
│          - Shipment_Tracker (distance: 8)
└─ Topic: returns
   └─ Action: process_return
      └─ Target: apex://ReturnProcessor         ✓ Found

Summary: 2/3 targets found (66.7%)
Exit code: 1 (missing targets detected)
```

### 5. I/O Parameter Validation

When the `--validate-io` flag is used, discover also validates that found targets have I/O parameters matching the `.agent` file declarations:

- **Flows:** Queries `/services/data/v63.0/actions/custom/flow/{FlowApiName}` to get actual input/output parameter schema. Compares names (case-sensitive) and types against `.agent` file declarations.
- **Apex:** Queries `ApexClass` body to check `@InvocableVariable` field names match expected inputs/outputs.

Validation results appear as warnings (non-blocking):

```
⚠️  I/O Mismatches (2):
   Get_Order_Status: input 'customer_name' not found in org target
   ProcessReturn: input 'order_id' type mismatch — expected number, got string
```

### 6. Classification for Scaffold Pipeline

Discovery feeds into scaffold with action classification:

| Signal in Description | Classification | Scaffold Output |
|----------------------|---------------|-----------------|
| "API", "HTTP", "REST", "external", URL patterns | `callout` | Apex with Http + Remote Site + Custom Metadata |
| SObject names, "query", "record", "SOQL" | `soql` | Apex with SOQL query logic |
| No special signals | `basic` | Standard placeholder Apex |

When `callout` is classified, scaffold additionally generates:
- Remote Site Settings for discovered domains
- Custom Metadata Type + record if auth keywords detected ("API key", "Bearer", "token")
- Apex test class with `HttpCalloutMock`

## Integration with Other Skills

### Next Steps After Discovery

If targets are missing, suggest running the scaffold skill:

```bash
# Generate stub metadata for missing targets
python3 "$ADLC_SCRIPTS/scaffold.py" -o <org-alias> --agent-file <path>
```

If all targets are found, suggest proceeding to deployment:

```bash
# Deploy agent bundle
sf agent publish authoring-bundle --api-name <AgentName> -o <org-alias>
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `No .agent files found` | Wrong directory or no agent bundles | Check `--agent-file` path or project structure |
| `Invalid org alias` | Org not authenticated | Run `sf org login web --alias <org-alias>` |
| `SOQL query failed` | Missing permissions | Ensure user has read access to Flow, ApexClass, etc. |
| `Invalid target format` | Malformed URI in .agent file | Fix syntax: `target: "flow://FlowName"` |

## Advanced Features

### Directory Discovery
When multiple `.agent` files exist, use `--agent-dir` to process all of them:

```bash
# Discover all agents in project
python3 "$ADLC_SCRIPTS/discover.py" -o <org-alias> --agent-dir force-app/main/default/aiAuthoringBundles
```

### CI/CD Integration
Exit codes for automation:
- `0`: All targets found
- `1`: Some targets missing (non-blocking warning)
- `2`: Critical error (no .agent files, auth failure)

```yaml
# GitHub Actions example
- name: Validate Agent Targets
  run: |
    python3 scripts/discover.py -o staging
    if [ $? -eq 2 ]; then
      echo "Critical error in discovery"
      exit 1
    fi
```

## Exit Codes

| Code | Meaning | Action Required |
|------|---------|-----------------|
| 0 | All targets found | Safe to deploy |
| 1 | Some targets missing | Review and scaffold missing targets |
| 2 | Critical failure | Fix authentication or file issues |