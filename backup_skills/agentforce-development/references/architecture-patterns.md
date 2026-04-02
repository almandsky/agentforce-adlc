# Architecture Patterns

> Extracted from SKILL.md Section 8. This file is loaded on demand when architecture pattern guidance is needed.

## Hub-and-Spoke (Most Common)

A central `topic_selector` routes to specialized spoke topics. Each spoke has a "back to hub" transition. Use when users may have multiple distinct intents.

```
start_agent topic_selector:
	description: "Route user requests to the appropriate topic"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions directly.
			Always use a transition action to route immediately.
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Order questions"
			to_returns: @utils.transition to @topic.return_support
				description: "Return or refund requests"
			to_general: @utils.transition to @topic.general_support
				description: "General questions"

topic order_support:
	description: "Handle order inquiries"
	reasoning:
		instructions: ->
			| Help the customer with their order.
		actions:
			lookup: @actions.get_order
				description: "Look up order"
			back: @utils.transition to @topic.topic_selector
				description: "Route to a different topic"
```

> **Routing lives in `start_agent`** -- put all transition actions directly in `start_agent topic_selector:`. Do NOT create a separate routing-only topic (e.g. `main_menu`, `central_hub`) -- that duplicates the router, adds an extra LLM hop (~3-5s latency), and confuses the platform. Topics that need "go back" should transition to `@topic.topic_selector`.

## Verification Gate

Users must pass through identity verification before accessing protected topics. Use when handling sensitive data, payments, or PII.

```
start_agent topic_selector:
	description: "Route through identity verification"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions directly.
			Route all users to identity verification first.
		actions:
			verify: @utils.transition to @topic.identity_verification
				description: "Begin verification"

topic identity_verification:
	description: "Verify customer identity"
	reasoning:
		instructions: ->
			if @variables.failed_attempts >= 3:
				| Too many failed attempts. Transferring to human agent.
				transition to @topic.escalation

			if @variables.is_verified == True:
				| Identity verified! How can I help?

			if @variables.is_verified == False:
				| Please verify your identity.

		actions:
			verify_email: @actions.verify_identity
				description: "Verify customer email"
				set @variables.is_verified = @outputs.verified

			to_account: @utils.transition to @topic.account_mgmt
				description: "Account management"
				available when @variables.is_verified == True

			escalate_now: @utils.escalate
				description: "Transfer to human"
```

## Post-Action Loop

The topic re-resolves after an action completes. Place post-action checks at the TOP of `instructions: ->` so they trigger on the loop:

```
reasoning:
	instructions: ->
		# POST-ACTION CHECK (at TOP - triggers on re-resolution)
		if @variables.refund_status == "Approved":
			run @actions.create_crm_case
				with customer_id = @variables.customer_id
			transition to @topic.confirmation

		# PRE-LLM: Load data
		run @actions.load_risk_score
			with customer_id = @variables.customer_id
			set @variables.risk_score = @outputs.score

		# DYNAMIC INSTRUCTIONS
		| Risk score: {!@variables.risk_score}
		if @variables.risk_score >= 80:
			| HIGH RISK - Offer retention package.
		else:
			| STANDARD - Follow normal process.
```

## Multi-Intent Handling

When a user sends multiple intents in one message, the start_agent router should handle the first intent and queue the second:

```
instructions: |
	You are a router only. Do NOT answer questions directly.
	If the user asks about multiple topics in one message, route to the first
	topic. After that task is complete, remind the user about the other request.
```

## Handling Incomplete Action Inputs

- Use `with param = ...` (slot-fill) for inputs the LLM should extract from conversation
- Add instructions that tell the LLM to invoke the action with whatever data is available
- Anti-pattern: Making the LLM ask for ALL inputs before invoking

## Controlling Opportunistic Action Chains

In long action chains (A->B->C->D), the LLM may invoke downstream actions as soon as prerequisites are met. To control this:

- Add explicit gating in instructions: "Only invoke generate_resolution if the user explicitly asks"
- Use `available when` guards on downstream actions
- Distinguish between "analyze only" and "full resolution" workflows in instructions

Anti-pattern: Leaving action chains ungated so the LLM runs the entire pipeline for every query.
