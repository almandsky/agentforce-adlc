---
name: adlc-deploy
description: Deploy, publish, and activate Agentforce agent bundles
allowed-tools: Bash Read Glob
argument-hint: "<org-alias> --api-name <AgentName> [--activate] [--dry-run]"
---

# ADLC Deploy

Full deployment lifecycle for Agentforce agents: validate, deploy metadata, publish bundle, and activate.

## Overview

This skill orchestrates the complete deployment pipeline for Agentforce agents, handling the complex multi-step process of getting an agent from development to production. It manages the proper sequencing of metadata deployment, bundle publishing, and agent activation.

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
# Basic deployment (validate + publish)
sf agent publish authoring-bundle --api-name MyAgent -o <org-alias> --json

# Full deployment with activation
python3 "$ADLC_SCRIPTS/deploy.py" \
  -o <org-alias> \
  --api-name MyAgent \
  --activate

# Dry run to see what would be deployed
python3 "$ADLC_SCRIPTS/deploy.py" \
  -o <org-alias> \
  --api-name MyAgent \
  --dry-run

# Deploy with specific source directory
python3 "$ADLC_SCRIPTS/deploy.py" \
  -o <org-alias> \
  --api-name MyAgent \
  --source-dir force-app \
  --activate
```

## Deployment Phases

### Phase 0: Safety Gate (Required)

Before deploying, read the `.agent` file and run a safety review using the `adlc-safety`
criteria (see `skills/adlc-safety/SKILL.md`). Evaluate against all 7 categories:
Identity & Transparency, User Safety, Data Handling, Content Safety, Fairness,
Deception & Manipulation, and Scope & Boundaries.

**If any BLOCK finding exists, STOP deployment and report the findings to the user.**
WARN findings should be reported but do not block deployment.

This is especially important for agents being deployed to production orgs — once published
and activated, a harmful agent is live and interacting with real users.

### Phase 1: Pre-Deployment Validation

```bash
# Validate agent bundle syntax
sf agent validate authoring-bundle --api-name MyAgent -o <org-alias> --json
```

Checks for:
- Valid Agent Script syntax
- Proper `default_agent_user` configuration
- All topic references resolve
- Action targets are properly formatted
- No mixed tabs/spaces indentation

Expected output:
```json
{
  "status": 0,
  "result": {
    "valid": true,
    "errors": [],
    "warnings": []
  }
}
```

### Phase 1b: Target Dependency Check

Before deploying, verify all action targets referenced in the `.agent` file exist in the org:

```bash
# Parse flow targets from the .agent file
grep -o 'flow://[A-Za-z0-9_]*' force-app/main/default/aiAuthoringBundles/<AgentName>/<AgentName>.agent | sort -u

# Parse apex targets
grep -o 'apex://[A-Za-z0-9_]*' force-app/main/default/aiAuthoringBundles/<AgentName>/<AgentName>.agent | sort -u

# For each flow target, check if it exists and is active
sf data query -q "SELECT ApiName FROM FlowDefinitionView WHERE ApiName = '<FlowApiName>' AND IsActive = true" -o <org> --json

# For each apex target, check if it exists
sf data query -q "SELECT Name FROM ApexClass WHERE Name = '<ClassName>' AND Status = 'Active'" -o <org> --json
```

If any targets are missing:
1. List the missing targets clearly
2. Ask if the user wants to scaffold stubs (invoke adlc-scaffold)
3. Or ask the user to create them manually
4. Do NOT proceed to publish until all targets exist

This step prevents the common "Flow not found" error that occurs when publishing an agent
with references to Flows or Apex classes that haven't been deployed yet.

### Phase 2: Deploy Supporting Metadata

Before publishing the agent, deploy all referenced metadata:

```bash
# Deploy flows, apex classes, and other dependencies
sf project deploy start --source-dir force-app -o <org-alias> --json
```

This deploys:
- **Flows** referenced by `flow://` targets
- **Apex classes** referenced by `apex://` targets
- **Prompt templates** for `generatePromptResponse://` targets
- **Custom objects and fields** used by actions
- **Permission sets** for agent access

Deployment verification:
```json
{
  "status": 0,
  "result": {
    "done": true,
    "id": "0AfXX000000XX",
    "status": "Succeeded",
    "numberComponentsDeployed": 15,
    "numberComponentsTotal": 15
  }
}
```

### Phase 3: Publish Agent Bundle

```bash
# Publish the agent authoring bundle
sf agent publish authoring-bundle --api-name MyAgent -o <org-alias> --json
```

This performs a 4-step process:
1. **Validate Bundle** (~1-2s) - Syntax and reference validation
2. **Publish Agent** (~8-10s) - Upload to Agentforce platform
3. **Retrieve Metadata** (~5-7s) - Sync generated components
4. **Deploy Metadata** (~4-6s) - Update org with agent metadata

Success response:
```json
{
  "status": 0,
  "result": {
    "agentId": "0XxXX000000XX",
    "versionId": "4KdXX000000XX",
    "status": "Published",
    "message": "Agent published successfully"
  }
}
```

**Troubleshooting "Internal Error, try again later":**
- If re-publishing an EXISTING agent works but creating a NEW agent fails with "Internal Error", this is a known platform issue (not an agent script problem).
- Workaround: Create the agent manually in Setup UI first (just the shell — name + type), then publish the authoring bundle to it. Re-publishing to an existing agent works reliably.
- This is a transient Salesforce platform issue. Retry after some time if the workaround isn't viable.

### Phase 4: Activate Agent

```bash
# Activate the published agent version
sf agent activate --api-name MyAgent -o <org-alias>
```

**Important**:
- Publishing creates an **inactive** version — the agent CANNOT be previewed or used until activated
- Without activation, `sf agent preview start` fails with `"No valid version available"` (HTTP 404)
- Activation makes it live for preview and end users
- Only one version can be active at a time
- `activate` command does NOT support `--json` flag

Verify activation:
```bash
sf data query \
  --query "SELECT DeveloperName, VersionNumber, Status FROM BotVersion WHERE BotDefinition.DeveloperName = 'MyAgent' AND Status = 'Active'" \
  -o <org-alias> --json
```

## Complete Deployment Script

The deployment script orchestrates all phases:

```python
#!/usr/bin/env python3
# $ADLC_SCRIPTS/deploy.py

import subprocess
import json
import sys
import time

def run_command(cmd, check=True):
    """Execute shell command and return result"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(result.returncode)
    return result

def validate_agent(api_name, org):
    """Phase 1: Validate agent bundle"""
    print(f"Validating {api_name}...")
    cmd = f"sf agent validate authoring-bundle --api-name {api_name} -o {org} --json"
    result = run_command(cmd)
    data = json.loads(result.stdout)

    if not data.get('result', {}).get('valid', False):
        print("Validation failed:")
        for error in data.get('result', {}).get('errors', []):
            print(f"  - {error}")
        sys.exit(1)

    print("✓ Validation passed")
    return True

def deploy_metadata(source_dir, org):
    """Phase 2: Deploy supporting metadata"""
    print(f"Deploying metadata from {source_dir}...")
    cmd = f"sf project deploy start --source-dir {source_dir} -o {org} --json"
    result = run_command(cmd)
    data = json.loads(result.stdout)

    if data.get('result', {}).get('status') != 'Succeeded':
        print("Deployment failed")
        sys.exit(1)

    deployed = data.get('result', {}).get('numberComponentsDeployed', 0)
    print(f"✓ Deployed {deployed} components")
    return True

def publish_agent(api_name, org):
    """Phase 3: Publish agent bundle"""
    print(f"Publishing {api_name}...")
    cmd = f"sf agent publish authoring-bundle --api-name {api_name} -o {org} --json"
    result = run_command(cmd)
    data = json.loads(result.stdout)

    if data.get('status') != 0:
        print(f"Publish failed: {data.get('message')}")
        sys.exit(1)

    version_id = data.get('result', {}).get('versionId')
    print(f"✓ Published version: {version_id}")
    return version_id

def activate_agent(api_name, org):
    """Phase 4: Activate agent"""
    print(f"Activating {api_name}...")
    cmd = f"sf agent activate --api-name {api_name} -o {org}"
    result = run_command(cmd, check=False)  # No --json support

    if "activated" in result.stdout.lower():
        print("✓ Agent activated")
        return True
    else:
        print(f"Activation unclear: {result.stdout}")
        return False

def main():
    # Parse arguments (simplified)
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--org', required=True)
    parser.add_argument('--api-name', required=True)
    parser.add_argument('--source-dir', default='force-app')
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN - would execute:")
        print(f"  1. Validate {args.api_name}")
        print(f"  2. Deploy {args.source_dir}")
        print(f"  3. Publish {args.api_name}")
        if args.activate:
            print(f"  4. Activate {args.api_name}")
        return

    # Execute deployment pipeline
    validate_agent(args.api_name, args.org)
    deploy_metadata(args.source_dir, args.org)
    version_id = publish_agent(args.api_name, args.org)

    if args.activate:
        time.sleep(2)  # Brief pause before activation
        activate_agent(args.api_name, args.org)

    print(f"\n✅ Deployment complete!")
    print(f"Agent: {args.api_name}")
    print(f"Version: {version_id}")
    print(f"Status: {'Active' if args.activate else 'Inactive (use --activate to make live)'}")

if __name__ == '__main__':
    main()
```

## Deploy vs Publish: What Each Propagates

| What changes | `sf project deploy start` | `sf agent publish authoring-bundle` |
|---|---|---|
| Bundle metadata (`.agent` file stored) | Yes | Yes |
| `system: instructions:` | Yes (via activate) | Yes |
| `topic: description:` (routing) | Yes (via activate) | Yes |
| `topic: reasoning: instructions:` | Partial (may not propagate) | Yes |
| `topic: reasoning: actions:` (transitions + invocations) | **NO** — topics show zero enabled tools | Yes |
| Creates new active version | Requires separate `sf agent activate` | Automatic |

**Key takeaway:** Always prefer `sf agent publish authoring-bundle`. Use deploy + activate only as a fallback for non-action changes. If you change `reasoning: actions:` in any topic, publish is required.

---

## Error Recovery

### Common Issues and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Required fields missing: [BundleType]` | Extra fields in bundle-meta.xml (`<developerName>`, `<masterLabel>`, `<description>`, `<target>`) | Use minimal bundle-meta.xml with ONLY `<bundleType>AGENT</bundleType>`. The publish command manages other fields automatically. |
| `Not available for deploy for this API version` | Using `sf project deploy start` on AiAuthoringBundle | Use `sf agent publish authoring-bundle`, not `sf project deploy` for agent bundles |
| `Internal Error, try again later` | Invalid default_agent_user | Query Einstein Agent Users and fix .agent file |
| `Duplicate value found: GenAiPluginDefinition` | `start_agent` and a `topic` share the same name (both create `GenAiPluginDefinition` records), or orphaned records from prior failed publishes | Rename `start_agent` or the colliding topic so they have different names, then re-publish. Orphaned records cannot be deleted (dependency errors). See known-issues.md Issue 13. |
| `No .agent file found` | developer_name mismatch | Ensure folder name matches developer_name |
| `Flow not found` | Metadata not deployed | Deploy flows before publishing agent |
| `SetupEntityType is not supported for DML` or `DML not allowed on PermissionSet` | Tried to create/update PermissionSet via Apex DML | Permission sets are **read-only via DML** — must use `sf project deploy start` (Metadata API). Generate `.permissionset-meta.xml` and deploy with the rest of the metadata. |

### Rollback Procedure

If deployment fails after partial completion:

```bash
# 1. Deactivate current version (if activated)
sf agent deactivate --api-name MyAgent -o <org>

# 2. Roll back to previous version
sf data query \
  --query "SELECT Id, VersionNumber FROM BotVersion WHERE BotDefinition.DeveloperName = 'MyAgent' ORDER BY VersionNumber DESC LIMIT 2" \
  -o <org> --json

# 3. Activate previous version
sf agent activate --api-name MyAgent --version-number <previous> -o <org>
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Deploy Agentforce Agent
on:
  push:
    branches: [main]
    paths:
      - 'force-app/**'
      - '.github/workflows/deploy-agent.yml'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install Salesforce CLI
        run: |
          npm install -g @salesforce/cli

      - name: Authenticate Org
        run: |
          echo "${{ secrets.SFDX_AUTH_URL }}" > auth.txt
          sf org login sfdx-url --sfdx-url-file auth.txt --alias production

      - name: Validate Agent
        run: |
          sf agent validate authoring-bundle \
            --api-name ${{ vars.AGENT_NAME }} \
            -o production --json

      - name: Deploy Metadata
        run: |
          sf project deploy start \
            --source-dir force-app \
            -o production --json

      - name: Publish Agent
        run: |
          sf agent publish authoring-bundle \
            --api-name ${{ vars.AGENT_NAME }} \
            -o production --json

      - name: Activate Agent
        if: github.ref == 'refs/heads/main'
        run: |
          sf agent activate \
            --api-name ${{ vars.AGENT_NAME }} \
            -o production
```

## Monitoring Deployment

### Health Checks

After deployment, verify agent health:

```bash
# Check active version
sf data query \
  --query "SELECT DeveloperName, VersionNumber, Status, LastModifiedDate FROM BotVersion WHERE BotDefinition.DeveloperName = 'MyAgent' AND Status = 'Active'" \
  -o <org> --json

# Check for recent errors (if Data Cloud enabled)
sf apex run -o <org> -f /dev/stdin << 'EOF'
String query = 'SELECT ssot__ErrorMessageText__c FROM ssot__AiAgentInteractionStep__dlm WHERE ssot__ErrorMessageText__c != null LIMIT 10';
ConnectApi.CdpQueryInput input = new ConnectApi.CdpQueryInput();
input.sql = query;
ConnectApi.CdpQueryOutputV2 result = ConnectApi.CdpQuery.queryAnsiSqlV2(input, 'default');
System.debug(JSON.serialize(result));
EOF
```

### Post-Deployment Testing

Run smoke tests immediately after deployment. Use `--authoring-bundle` to generate local trace files for verification:

```bash
# Start preview session (--authoring-bundle generates local traces)
SESSION_ID=$(sf agent preview start --authoring-bundle MyAgent -o <org> --json | jq -r '.result.sessionId')

# Send test utterance
sf agent preview send \
  --session-id "$SESSION_ID" \
  --authoring-bundle MyAgent \
  --utterance "Hello, I need help" \
  -o <org> --json

# End session
sf agent preview end --session-id "$SESSION_ID" --authoring-bundle MyAgent -o <org> --json
```

> **Note:** Use `--api-name` instead of `--authoring-bundle` to test the last-published version (no local traces generated).

## Best Practices

### Pre-Deployment Checklist

- [ ] All action targets exist in org (run discover first)
- [ ] Agent Script validated locally (no syntax errors)
- [ ] Einstein Agent User configured correctly
- [ ] Supporting metadata deployed (flows, apex, objects)
- [ ] Previous version backed up
- [ ] Rollback plan documented

### Deployment Windows

- Deploy during low-traffic periods
- Keep previous version active until new version is tested
- Use staging org for final validation before production
- Maintain deployment log for audit trail

### Version Management

- Tag git commits with agent version numbers
- Document changes in each version
- Keep mapping of git commits to BotVersion IDs
- Archive deprecated versions before deletion

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Deployment successful | Proceed with testing |
| 1 | Validation or deployment failed | Review errors and fix |
| 2 | Critical failure (auth, network) | Check connectivity and credentials |

---

## Feedback

**On success:** After a successful deploy + activate, mention feedback briefly:

```
Deployment complete! If anything in the process was confusing or could be smoother,
you can run /adlc-feedback to share quick feedback.
```

**On persistent errors:** If the user hits errors that take multiple retries to resolve, offer feedback as a way to help improve the tooling:

```
That was a tricky one to get past. If you'd like, run /adlc-feedback so we can
capture what went wrong — it helps improve the deploy skill for next time.
```

Only mention feedback once per session. Do not repeat if the user ignores it.