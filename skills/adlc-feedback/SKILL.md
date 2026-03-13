---
name: adlc-feedback
description: Collect and submit feedback on ADLC skills to help improve the toolchain
allowed-tools: Bash Read Glob
argument-hint: "[--about <skill-name>]"
---

# ADLC Feedback

Collect structured feedback about the ADLC skills and submit it via a Google Form so the maintainers can improve the toolchain.

## Design Principles

- **Minimize user effort** — Auto-draft feedback from conversation context. The user only needs to confirm or tweak.
- **One confirmation** — Combine consent + review into a single step. Show the draft, let them approve/edit/cancel.
- **Non-intrusive** — Never push. If the user ignores the suggestion, move on.

## Feedback Form URL

```
https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=<URL-encoded suggestions>
```

The `entry.2121871774` parameter pre-fills the Suggestions field. The user fills in other fields directly on the form.

## Workflow

### Step 1: Auto-Draft Feedback from Conversation

Silently review the current conversation to extract:

1. **Skills used** — Which `/adlc-*` skills were invoked
2. **Agent name** — The `.agent` file being worked on (if any)
3. **Outcome** — Did the task succeed? Were there errors or retries?
4. **Pain points** — Any friction, confusion, or unexpected behavior
5. **Workarounds** — Did the user have to work around skill limitations?

Compose a concise feedback summary (under 1500 characters):

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
```

### Step 2: Present Draft and Ask for Consent + Approval (Single Step)

Show the auto-drafted feedback and combine consent with review in one message:

```
I drafted some quick feedback based on our session. This will be submitted via
a Google Form — no source code, credentials, or org data is included.

<draft summary>

Want to:
1. Submit (opens form with this pre-filled)
2. Edit (tell me what to change)
3. Skip
```

This is the ONLY question you need to ask. Do not add a separate consent step.

**If the user says skip/no/cancel**, stop immediately. Do not ask why.

**If the user says edit**, apply their changes and show the updated draft once more.

**If the user says submit/yes/1**, proceed to Step 3.

**If the user provides additional comments** (e.g., "yes, also the scaffold was slow"), incorporate their comments into the summary before submitting.

### Step 3: Submit via Google Form

URL-encode the feedback summary and open the form:

```bash
# URL-encode the feedback summary
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''<feedback summary>'''))")

# Open the form with pre-filled Suggestions field
FORM_URL="https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=${ENCODED}"

# macOS
open "$FORM_URL"
# Linux: xdg-open "$FORM_URL"
# Windows: start "$FORM_URL"
```

Tell the user:

```
Form opened in your browser. Review it and click Submit when ready.
```

That's it. Do not follow up or ask if they submitted.

## When This Skill Gets Triggered

This skill is invoked in two ways:

### 1. Directly by the user
The user says `/adlc-feedback` or "I want to give feedback". Follow the full workflow above.

### 2. Suggested by other ADLC skills
Other skills suggest `/adlc-feedback` at natural moments:

- **On completion** — After a successful author/deploy/test/optimize cycle
- **On persistent errors** — After the user struggles with repeated failures
- **On workarounds** — When the user had to work around a skill limitation

When triggered by suggestion, the user has already been working with ADLC skills,
so the conversation context is rich. The auto-draft should be high quality with
minimal user input needed.

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
- If the user declines, respect their decision immediately

## Example

User: `/adlc-feedback`

Agent auto-drafts from conversation context and presents:

```
I drafted some quick feedback based on our session. This will be submitted via
a Google Form — no source code, credentials, or org data is included.

Skills: adlc-author, adlc-deploy
Agent: OrderService
Date: 2026-03-12

What Worked:
- Agent authoring generated valid .agent file on first try
- Discover correctly identified 3 missing flow targets

Issues:
- sf agent publish timed out twice before succeeding on third attempt
- Had to manually add --wait 10 flag

Suggestions:
- Add automatic retry with backoff for publish timeouts
- Default to longer wait time for publish command

Want to:
1. Submit (opens form with this pre-filled)
2. Edit (tell me what to change)
3. Skip
```

User: "yes"

Agent opens: `https://docs.google.com/forms/d/e/1FAIpQLSdBbFIW0Q71NoVts6oboqDcjkGcrryXEzu0W2FypNS8bBF5cg/viewform?usp=pp_url&entry.2121871774=Skills%3A%20adlc-author%2C%20adlc-deploy%0A...`

```
Form opened in your browser. Review it and click Submit when ready.
```
