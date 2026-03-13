---
name: adlc-scaffold
description: Generate Flow XML and Apex stubs for missing action targets in .agent files
allowed-tools: Bash Read Write Edit Glob Grep
argument-hint: "<org-alias> [--agent-file <path>] [--output-dir <path>]"
---

# ADLC Scaffold

Generate stub metadata files (Flow XML, Apex classes) for Agent Script targets that don't exist in the org, with SObject-aware field discovery when connected.

## Overview

This skill automatically generates Salesforce metadata stubs for missing action targets referenced in `.agent` files. It creates properly structured Flow XML files and Apex InvocableMethod classes based on the input/output schemas defined in your Agent Script, with intelligent field mapping when connected to an org.

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

## Usage

The script auto-configures `sys.path`, so it can be run from any directory. Use `python3` on macOS/Linux, `python` on Windows:

```bash
# Scaffold missing targets (runs discover first)
python3 "$ADLC_SCRIPTS/scaffold.py" \
  --agent-file path/to/Agent.agent -o <org-alias> --output-dir force-app/main/default

# Scaffold all targets without checking org (use --all flag)
python3 "$ADLC_SCRIPTS/scaffold.py" \
  --agent-file path/to/Agent.agent --all --output-dir force-app/main/default

# From the project root (also works)
python3 scripts/scaffold.py --agent-file path/to/Agent.agent -o <org-alias>
```

## What it does

### 1. Discovery Phase (unless --all)
- Runs the discover workflow to identify missing targets
- Extracts input/output schemas from the `.agent` file for each action
- Maps Agent Script types to Salesforce data types

### 2. Metadata Generation

#### For `flow://` Targets

Generates a complete Flow XML file with:
- **Input variables** based on action `inputs:` definition
- **Output variables** based on action `outputs:` definition
- **Assignment elements** as placeholder logic
- **Start element** properly configured
- **API version** matching project settings

Example generated Flow structure:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Flow xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>63.0</apiVersion>
    <description>Scaffolded flow for Get_Order_Status action</description>
    <label>Get Order Status</label>

    <!-- Input variables from .agent file -->
    <variables>
        <name>orderId</name>
        <dataType>String</dataType>
        <isInput>true</isInput>
        <isOutput>false</isOutput>
    </variables>

    <!-- Output variables from .agent file -->
    <variables>
        <name>orderStatus</name>
        <dataType>String</dataType>
        <isInput>false</isInput>
        <isOutput>true</isOutput>
    </variables>

    <!-- Placeholder logic -->
    <assignments>
        <name>Set_Output</name>
        <label>Set Output Values</label>
        <locationX>176</locationX>
        <locationY>134</locationY>
        <assignmentItems>
            <assignToReference>orderStatus</assignToReference>
            <operator>Assign</operator>
            <value>
                <stringValue>TODO: Implement Get_Order_Status logic</stringValue>
            </value>
        </assignmentItems>
    </assignments>

    <start>
        <locationX>50</locationX>
        <locationY>0</locationY>
        <connector>
            <targetReference>Set_Output</targetReference>
        </connector>
    </start>

    <status>Draft</status>
    <processType>AutoLaunchedFlow</processType>
</Flow>
```

#### For `apex://` Targets

Generates Apex class with @InvocableMethod:
- **Input wrapper class** with @InvocableVariable properties
- **Output wrapper class** for return values
- **@InvocableMethod** with proper annotations
- **Test class** with 75% coverage boilerplate

Example generated Apex class:
```apex
public with sharing class OrderProcessor {

    public class InputWrapper {
        @InvocableVariable(label='Order ID' required=true)
        public String orderId;

        @InvocableVariable(label='Action Type' required=false)
        public String actionType;
    }

    public class OutputWrapper {
        @InvocableVariable(label='Success')
        public Boolean success;

        @InvocableVariable(label='Message')
        public String message;

        @InvocableVariable(label='Order Data')
        public Order orderData;
    }

    @InvocableMethod(
        label='Process Order'
        description='Processes order based on action type'
        category='Order Management'
    )
    public static List<OutputWrapper> processOrder(List<InputWrapper> inputs) {
        List<OutputWrapper> outputs = new List<OutputWrapper>();

        for (InputWrapper input : inputs) {
            OutputWrapper output = new OutputWrapper();

            // TODO: Implement actual business logic
            output.success = true;
            output.message = 'Order processed: ' + input.orderId;

            outputs.add(output);
        }

        return outputs;
    }
}
```

### 3. Action Classification

Before generating stubs, scaffold classifies each action to determine the appropriate output strategy:

| Signal in Description | Classification | Generated Files |
|----------------------|---------------|-----------------|
| "API", "HTTP", "REST", "external", URL | `callout` | Apex with `Http`/`HttpRequest`/`HttpResponse` + test with `HttpCalloutMock` + Remote Site Settings + Custom Metadata (if auth detected) |
| "query", "record", "SObject", "SOQL" | `soql` | Apex with SOQL query logic (SObject-aware) + test class |
| No special signals | `basic` | Standard placeholder Apex + test class |

**Callout scaffold** includes:
- Apex class with HTTP callout boilerplate (`Http`, `HttpRequest`, `HttpResponse`, `JSON.deserializeUntyped`)
- Remote Site Setting XML for each domain found in the action description
- Custom Metadata Type (`__mdt`) + default record with `apikey__c` field when auth keywords detected ("API key", "Bearer", "token")
- Test class with `HttpCalloutMock` inner class and `Test.setMock()`

**Complete output for a callout action:**
```
force-app/main/default/
├── classes/
│   ├── FetchWeatherData.cls              # Apex with Http boilerplate
│   ├── FetchWeatherData.cls-meta.xml
│   ├── FetchWeatherDataTest.cls          # Test with HttpCalloutMock
│   └── FetchWeatherDataTest.cls-meta.xml
├── remoteSiteSettings/
│   └── api_weather_com.remoteSite-meta.xml
├── customMetadata/
│   └── FetchWeatherData_Config.Default.md-meta.xml
├── objects/
│   └── FetchWeatherData_Config__mdt/
│       ├── FetchWeatherData_Config__mdt.object-meta.xml
│       └── fields/
│           └── apikey__c.field-meta.xml
└── permissionsets/
    └── Agent_Action_Access.permissionset-meta.xml
```

### 4. SObject-Aware Generation

When connected to an org, the scaffold tool:
- **Queries SObject metadata** for referenced object types
- **Validates field existence** for complex data types
- **Generates accurate SOQL queries** in Apex stubs
- **Creates proper field mappings** in Flow Get Records elements

Example with SObject awareness:
```apex
// If .agent file references Order object fields
Order orderRecord = [
    SELECT Id, OrderNumber, Status, TotalAmount, AccountId
    FROM Order
    WHERE Id = :input.orderId
    LIMIT 1
];
```

### 4. Type Mapping

Agent Script to Salesforce type conversion:

| Agent Script Type | Flow Variable Type | Apex Type |
|-------------------|-------------------|-----------|
| `string` | `String` | `String` |
| `number` | `Number` | `Decimal` |
| `boolean` | `Boolean` | `Boolean` |
| `date` | `Date` | `Date` |
| `datetime` | `DateTime` | `DateTime` |
| `id` | `String` | `Id` |
| `object` | `Apex` (SObject) | `SObject` or custom class |
| `list[string]` | `String` (multipicklist) | `List<String>` |
| `list[object]` | `Apex` (SObject collection) | `List<SObject>` |

### 5. Complex Data Type Handling

For Agent Script complex data types:
```yaml
# In .agent file
outputs:
  order_data:
    type: object
    complex_data_type_name: Order
    fields:
      - OrderNumber
      - Status
      - Account.Name
```

Generates appropriate metadata:
- **Flow**: Creates SObject variable with proper field references
- **Apex**: Generates SOQL with relationship queries

## Output Structure

Generated files follow Salesforce DX project structure:

```
force-app/main/default/
├── flows/
│   ├── Get_Order_Status.flow-meta.xml
│   └── Process_Return.flow-meta.xml
├── classes/
│   ├── OrderProcessor.cls
│   ├── OrderProcessor.cls-meta.xml
│   ├── OrderProcessorTest.cls
│   └── OrderProcessorTest.cls-meta.xml
└── promptTemplates/
    ├── Customer_Response.promptTemplate-meta.xml
    └── Order_Summary.promptTemplate-meta.xml
```

## Integration Workflow

### Complete ADLC Pipeline

1. **Discover** missing targets:
```bash
python3 scripts/discover.py -o myorg --agent-file MyAgent.agent
```

2. **Scaffold** stub metadata:
```bash
python3 scripts/scaffold.py -o myorg --agent-file MyAgent.agent
```

3. **Edit** generated stubs to add business logic

4. **Deploy** to org:
```bash
sf project deploy start --source-dir force-app/main/default -o myorg
```

5. **Verify** all targets now exist:
```bash
python3 scripts/discover.py -o myorg --agent-file MyAgent.agent
# Should show 100% targets found
```

6. **Publish** agent:
```bash
sf agent publish authoring-bundle --api-name MyAgent -o myorg
```

## Advanced Features

### Incremental Scaffolding

Only generates stubs for missing targets:
```bash
# First run: generates 5 missing flows
python3 scripts/scaffold.py -o myorg --agent-file MyAgent.agent

# After deploying 3 flows, second run only generates remaining 2
python3 scripts/scaffold.py -o myorg --agent-file MyAgent.agent
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `Invalid I/O schema` | Malformed inputs/outputs in .agent | Fix Agent Script syntax |
| `Unknown SObject type` | Referenced object doesn't exist | Create custom object first |
| `Field not found on SObject` | Invalid field reference | Check field API names |
| `Permission denied` | Can't write to output directory | Check file permissions |

## Best Practices

### I/O Variable Matching

Scaffolded Flow and Apex stubs MUST have input/output variable names that **exactly match** the `.agent` file's action I/O definitions. A mismatch causes `ACTION_ERROR` at runtime because the agent passes inputs and reads outputs by exact API name.

```
# .agent file defines these I/O names:
get_order_status:
   inputs:
      order_id: string          # Flow variable must be named "order_id"
   outputs:
      status: string            # Flow variable must be named "status"
      tracking_number: string   # Flow variable must be named "tracking_number"
```

When scaffolding:
- **Flow XML**: `<variables>` elements must use the exact `name` from `.agent` inputs/outputs, with `isInput`/`isOutput` set correctly
- **Apex InvocableMethod**: `@InvocableVariable` names must match exactly
- **Case sensitivity matters**: `order_id` ≠ `Order_Id` ≠ `orderId`

If you rename I/O variables in the `.agent` file after scaffolding, update the Flow/Apex stubs to match — or re-scaffold.

### Post-Scaffolding Steps

1. **Review generated code** - Stubs contain TODO comments marking where to add logic
2. **Add business logic** - Replace placeholder assignments with actual implementation
3. **Update test classes** - Scaffold generates basic tests; add meaningful assertions
4. **Handle errors** - Add try-catch blocks and proper error handling
5. **Add security** - Implement FLS/CRUD checks in Apex code

### Flow Best Practices

Generated flows are in Draft status. Before activation:
- Add error handling with fault paths
- Implement proper record locking
- Add decision elements for conditional logic
- Set up logging/debugging as needed

### Apex Best Practices

Generated Apex classes need:
- Bulkification for collection processing
- Governor limit management
- Sharing rules enforcement (`with sharing`)
- Comprehensive test coverage (aim for >85%)

## Performance Optimization

- Caches SObject describe calls to minimize API requests
- Generates files in parallel when multiple targets exist
- Reuses templates to avoid repeated parsing
- Typical generation time: <1 second per target

## Exit Codes

| Code | Meaning | Next Step |
|------|---------|-----------|
| 0 | Successfully generated all stubs | Review and customize generated code |
| 1 | Some stubs failed to generate | Check error messages, fix issues |
| 2 | Critical failure | Verify org connection and file permissions |

---

## Feedback

After scaffolding completes, if the generated stubs needed significant manual edits or if something
didn't work as expected, briefly mention:

```
If the generated stubs needed a lot of manual tweaking, run /adlc-feedback —
it helps us improve the generators for next time.
```

Only mention feedback once per session. Do not repeat if the user ignores it.