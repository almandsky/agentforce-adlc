# Naming Conventions & Gotchas

> Extracted from SKILL.md Sections 5, 7, 11. This file is loaded on demand when naming rules or common pitfalls are needed.

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Agent name | PascalCase or underscore-separated | `MyServiceAgent` |
| `developer_name` | Must match folder name exactly | `MyServiceAgent` |
| Topic names | snake_case | `order_support` |
| Variable names | camelCase or snake_case (consistent) | `order_id` |
| Action definitions (Level 1) | snake_case | `get_order_status` |
| Action invocations (Level 2) | snake_case | `lookup_order` |
| Labels | Human-readable with spaces | `"Order Support"` |

Rules:
- Only letters, numbers, underscores
- Must begin with a letter
- No spaces, no consecutive underscores, cannot end with underscore
- Maximum 80 characters
- **Apex class names**: Limited to 40 characters (Salesforce platform limit)

## Deployment Gotchas

| WRONG | CORRECT |
|-------|---------|
| `AgentName.aiAuthoringBundle-meta.xml` | `AgentName.bundle-meta.xml` |
| bundle-meta.xml with extra fields | Minimal: only `<bundleType>AGENT</bundleType>` |
| `sf project deploy start` for agents | `sf agent publish authoring-bundle --api-name X -o Org` |
| `sf agent validate --source-dir` | `sf agent validate authoring-bundle --api-name X -o Org` |
| Query Einstein Agent User from wrong org | Query TARGET org with `-o` flag |
| Publish and assume active | Run `sf agent activate` separately |
| `start_agent` and `topic` share name | Use different names |

### Bundle Directory Structure

```
force-app/main/default/aiAuthoringBundles/MyAgent/
  MyAgent.agent              # Agent Script file
  MyAgent.bundle-meta.xml    # NOT .aiAuthoringBundle-meta.xml
```

### Einstein Agent User Format

- Production: `username@orgid.ext`
- Dev/Scratch: `username.suffix@orgfarm.salesforce.com`

ALWAYS query the target org. Never guess.

### Deployment Lifecycle

```
Validate -> Publish -> Activate -> (Deactivate -> Re-publish -> Re-activate)
```

```bash
sf agent validate authoring-bundle --api-name MyAgent -o TargetOrg --json
sf agent publish authoring-bundle --api-name MyAgent -o TargetOrg --json
sf agent activate --api-name MyAgent -o TargetOrg  # no --json support
sf org open authoring-bundle -o TargetOrg
```

## Production Gotchas

### Credit Consumption
- Framework operations (`@utils.*`, `if`/`else`, `set`, lifecycle hooks) are FREE
- Flow/Apex/API actions cost 20 credits each per invocation
- Minimize action calls by caching results in variables

### Lifecycle Hooks
- `before_reasoning:` and `after_reasoning:` content goes DIRECTLY under the block
- There is NO `instructions:` wrapper inside lifecycle hooks
- Use `filter_from_agent: True` + `is_used_by_planner: True` on outputs for zero-hallucination routing

### Latch Variable Pattern

Prevent re-execution of one-time actions:
```
if @variables.data_loaded == False:
	run @actions.load_data
		with id = @variables.customer_id
		set @variables.customer_name = @outputs.name
	set @variables.data_loaded = True
```

### Token Limits
Large agents with many topics can exceed token limits. Keep instructions concise. Use `filter_from_agent: True` on actions that should not appear in the planner prompt.
