# Scaffold -- Stub Generation Reference

> Extracted from SKILL.md Section 17. This file is loaded on demand when scaffold details are needed.

## Overview

Generates stub metadata files (Flow XML, Apex classes) for Agent Script targets that don't exist in the org, with SObject-aware field discovery when connected.

## Usage

```bash
# Scaffold missing targets (runs discover first)
python3 "$ADLC_SCRIPTS/scaffold.py" \
  --agent-file path/to/Agent.agent -o <org-alias> --output-dir force-app/main/default

# Scaffold all targets without checking org
python3 "$ADLC_SCRIPTS/scaffold.py" \
  --agent-file path/to/Agent.agent --all --output-dir force-app/main/default
```

## What it does

### 1. Discovery Phase (unless --all)
- Runs discover to identify missing targets
- Extracts I/O schemas from the `.agent` file
- Maps Agent Script types to Salesforce types

### 2. Flow Generation (`flow://` targets)
Generates complete Flow XML with input/output variables, assignment placeholders, and start element.

### 3. Apex Generation (`apex://` targets)
Generates Apex class with `@InvocableMethod`, input/output wrapper classes, and test class with 75% coverage boilerplate.

### 4. Action Classification

| Signal | Classification | Generated Files |
|--------|---------------|-----------------|
| "API", "HTTP", "REST", URL | `callout` | Apex + `HttpCalloutMock` test + Remote Site + Custom Metadata |
| "query", "record", "SOQL" | `soql` | Apex with SOQL logic + test |
| No special signals | `basic` | Standard placeholder Apex + test |

### 5. SObject-Aware Generation
When connected to an org:
- Queries SObject metadata for referenced types
- Generates accurate SOQL queries in Apex stubs
- Creates proper field mappings in Flow elements

### 6. Type Mapping

| Agent Script | Flow Type | Apex Type |
|-------------|-----------|-----------|
| `string` | `String` | `String` |
| `number` | `Number` | `Decimal` |
| `boolean` | `Boolean` | `Boolean` |
| `date` | `Date` | `Date` |
| `id` | `String` | `Id` |
| `object` | `Apex` (SObject) | `SObject` |
| `list[string]` | `String` (multipicklist) | `List<String>` |

## Output Structure

```
force-app/main/default/
  flows/
    Get_Order_Status.flow-meta.xml
  classes/
    OrderProcessor.cls
    OrderProcessor.cls-meta.xml
    OrderProcessorTest.cls
    OrderProcessorTest.cls-meta.xml
  permissionsets/
    Agent_Action_Access.permissionset-meta.xml
```

## Best Practices

### I/O Variable Matching
Scaffolded stubs MUST have I/O names that **exactly match** the `.agent` file. Case sensitivity matters: `order_id` != `Order_Id` != `orderId`.

### Flow XML Element Ordering (CRITICAL)
All elements of the same type MUST be grouped together. Interleaved elements cause Metadata API rejection.

Recommended order: `apiVersion` -> `description` -> `label` -> `variables` -> `assignments` -> `decisions` -> `recordLookups` -> `recordCreates` -> `recordUpdates` -> `start` -> `status` -> `processType`

### Post-Scaffolding Steps
1. Review generated code (stubs have TODO comments)
2. Add business logic
3. Update test classes with meaningful assertions
4. Add error handling and FLS/CRUD checks

## Integration Workflow

```bash
# 1. Discover missing targets
python3 scripts/discover.py -o myorg --agent-file MyAgent.agent
# 2. Scaffold stubs
python3 scripts/scaffold.py -o myorg --agent-file MyAgent.agent
# 3. Edit stubs with business logic
# 4. Deploy to org
sf project deploy start --source-dir force-app/main/default -o myorg
# 5. Verify
python3 scripts/discover.py -o myorg --agent-file MyAgent.agent
# 6. Publish agent
sf agent publish authoring-bundle --api-name MyAgent -o myorg
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All stubs generated |
| 1 | Some stubs failed |
| 2 | Critical failure |
