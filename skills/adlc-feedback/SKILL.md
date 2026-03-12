---
name: adlc-feedback
description: Collect and submit feedback on ADLC skills to help improve the toolchain
allowed-tools: Bash Read Glob
argument-hint: "[--about <skill-name>]"
---

# ADLC Feedback

Collect structured feedback about the ADLC skills and submit it via a Google Form so the maintainers can improve the toolchain.

## Feedback Form URL

```
https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=<URL-encoded suggestions>
```

The `entry.2121871774` parameter pre-fills the Suggestions field. The user can fill in other fields directly on the form.

## Workflow

### Step 1: Ask for Permission

Before gathering any data, you MUST get explicit user consent:

```
I'd like to collect feedback about your experience with the ADLC skills.
This will include:
- A summary of what you were working on (skill used, agent name)
- What went well and what didn't
- Any errors or unexpected behavior encountered
- Your suggestions for improvement

No source code, credentials, or org data will be included.

Do you consent to sharing this feedback? (yes/no)
```

**If the user says no, stop immediately.** Do not collect or generate any feedback.

### Step 2: Gather Context from the Conversation

Review the current conversation to extract:

1. **Skills used** — Which `/adlc-*` skills were invoked in this session
2. **Agent name** — The `.agent` file being worked on (if any)
3. **Org alias** — The target org (if any, do NOT include org IDs or credentials)
4. **Outcome** — Did the task succeed? Were there errors or retries?
5. **Pain points** — Any friction, confusion, or unexpected behavior
6. **Workarounds** — Did the user have to work around skill limitations?

### Step 3: Ask the User for Their Input

After gathering context, ask the user directly:

```
Based on our session, here's what I observed. Please add your thoughts:

1. What were you trying to accomplish?
2. What worked well?
3. What was frustrating or confusing?
4. Any feature requests or suggestions?
```

### Step 4: Generate Feedback Summary

Compose a concise feedback summary. This will be pre-filled into the form's Suggestions field.
Keep it under 1500 characters to fit in a URL parameter.

Format:

```
Skills: <comma-separated list>
Agent: <agent name or N/A>
Date: <YYYY-MM-DD>

What Worked:
- <bullet points>

Issues:
- <bullet points>

Suggestions:
- <bullet points>

User Comments:
<verbatim user input from Step 3>
```

### Step 5: User Review

Show the feedback summary and ask the user to review:

```
Here's the feedback I've prepared:

<summary>

Would you like to:
1. Submit as-is (opens form with pre-filled suggestions)
2. Edit something (tell me what to change)
3. Cancel
```

### Step 6: Submit via Google Form

Once approved, URL-encode the feedback summary and open the form in the browser:

```bash
# URL-encode the feedback summary
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''<feedback summary>'''))")

# Open the form with pre-filled Suggestions field
FORM_URL="https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=${ENCODED}"

# macOS
open "$FORM_URL"
# Linux: xdg-open "$FORM_URL"
```

Inform the user:
```
Feedback form opened in your browser with pre-filled suggestions.
Please review the form, fill in any additional fields, and click Submit.
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--about` | (auto-detected) | Which skill to focus feedback on |

## Privacy Guidelines

- NEVER include org IDs, session IDs, or access tokens
- NEVER include source code or .agent file contents
- NEVER include SOQL query results or record data
- NEVER include credentials or API keys
- Only include skill names, error messages, and user-provided comments
- Always get explicit consent before collecting feedback
- If the user declines, respect their decision immediately

## Example

User: `/adlc-feedback`

```
I'd like to collect feedback about your experience with the ADLC skills.
This will include a summary of what you worked on, what went well,
and what could be improved. No source code or credentials will be shared.

Do you consent to sharing this feedback? (yes/no)
```

User: "yes, the deploy skill kept failing on publish"

Generated summary:
```
Skills: adlc-author, adlc-deploy
Agent: OrderService
Date: 2026-03-12

What Worked:
- Agent authoring completed successfully
- Deployment of prerequisites worked

Issues:
- sf agent publish failed 3 times with timeout errors
- Had to manually retry with longer timeout

Suggestions:
- Add automatic retry with backoff for publish failures
- Show clearer progress indicator during publish

User Comments:
"the deploy skill kept failing on publish"
```

Then opens: `https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=Skills%3A%20adlc-author%2C%20adlc-deploy%0A...`

The user reviews the form in the browser and clicks Submit.
