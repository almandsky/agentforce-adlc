# Complete Agent Examples

> Extracted from SKILL.md Sections 9 + 10. This file is loaded on demand when complete agent examples are needed.

## Minimal Service Agent

This is the absolute minimum for a deployable service agent:

```
system:
	instructions: "You are a helpful customer service agent."
	messages:
		welcome: "Hello! How can I help you today?"
		error: "Something went wrong. Please try again."

config:
	developer_name: "MinimalAgent"
	agent_label: "Minimal Agent"
	description: "A minimal service agent"
	default_agent_user: "agent@00dxx000001234.ext"

variables:
	EndUserId: linked string
		source: @MessagingSession.MessagingEndUserId
		description: "Messaging End User ID"
		visibility: "External"
	RoutableId: linked string
		source: @MessagingSession.Id
		description: "Messaging Session ID"
		visibility: "External"
	ContactId: linked string
		source: @MessagingEndUser.ContactId
		description: "Contact ID"
		visibility: "External"

language:
	default_locale: "en_US"
	additional_locales: ""
	all_additional_locales: False

start_agent topic_selector:
	description: "Begin the onboarding flow"

topic greeting:
	label: "Greeting"
	description: "Greet users and provide help"
	reasoning:
		instructions: ->
			| Welcome the user warmly.
			| Ask how you can help them today.
```

Companion `bundle-meta.xml` (MUST be this exact content -- no extra fields):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<AiAuthoringBundle xmlns="http://soap.sforce.com/2006/04/metadata">
  <bundleType>AGENT</bundleType>
</AiAuthoringBundle>
```

---

## Multi-Topic Agent with Actions

```
system:
	instructions: |
		You are a customer service agent for TechCorp.
		Be professional, concise, and solution-oriented.
		Always verify the customer before sensitive operations.
	messages:
		welcome: "Welcome to TechCorp Support! How can I assist you?"
		error: "I apologize for the issue. Please try again."

config:
	developer_name: "TechCorpAgent"
	agent_label: "TechCorp Support Agent"
	description: "Handles order inquiries, returns, and general support"
	default_agent_user: "einstein@00dxx000001234.ext"

variables:
	EndUserId: linked string
		source: @MessagingSession.MessagingEndUserId
		description: "Messaging End User ID"
		visibility: "External"
	RoutableId: linked string
		source: @MessagingSession.Id
		description: "Messaging Session ID"
		visibility: "External"
	ContactId: linked string
		source: @MessagingEndUser.ContactId
		description: "Contact ID"
		visibility: "External"
	order_id: mutable string = ""
		description: "Current order being discussed"
	order_status: mutable string = ""
		description: "Status of the current order"
	is_verified: mutable boolean = False
		description: "Customer verification status"
	case_id: mutable string = ""
		description: "Created case ID"

language:
	default_locale: "en_US"
	additional_locales: ""
	all_additional_locales: False

start_agent topic_selector:
	description: "Route customers to the right support topic"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions or provide help directly.
			Always use a transition action to route to the correct topic immediately.
			- Order status or tracking -> use to_orders
			- Returns or refunds -> use to_returns
			- General questions -> use to_general
			Never attempt to help the customer yourself. Always route.
		actions:
			to_orders: @utils.transition to @topic.order_support
				description: "Check order status or tracking"
			to_returns: @utils.transition to @topic.return_support
				description: "Process a return or refund"
			to_general: @utils.transition to @topic.general_support
				description: "General questions and support"

topic order_support:
	label: "Order Support"
	description: "Handle order status and tracking inquiries"

	actions:
		get_order:
			description: "Look up order by ID"
			target: "flow://Get_Order_Status"
			inputs:
				order_id: string
					description: "Order ID"
			outputs:
				status: string
					description: "Order status"
					is_displayable: True
				tracking_url: string
					description: "Tracking URL"
					is_displayable: True

	reasoning:
		instructions: ->
			if @variables.order_status != "":
				| Order {!@variables.order_id} status: {!@variables.order_status}

			| What is your order number? I will look it up for you.
			| Use the get_order action to retrieve order details.
			| Do not guess order status -- always use the action result.

		actions:
			lookup: @actions.get_order
				description: "Look up order"
				with order_id = ...
				set @variables.order_id = @outputs.order_id
				set @variables.order_status = @outputs.status

			back: @utils.transition to @topic.topic_selector
				description: "Route to a different topic"

topic return_support:
	label: "Return Support"
	description: "Handle returns and refund requests"

	actions:
		initiate_return:
			description: "Start a return process"
			target: "flow://Initiate_Return"
			inputs:
				order_id: string
					description: "Order ID for the return"
				reason: string
					description: "Reason for return"
			outputs:
				return_id: string
					description: "Return authorization ID"
					is_displayable: True

	reasoning:
		instructions: ->
			| I can help with your return request.
			| Please provide your order number and the reason for the return.
			| Use the initiate_return action to start the process -- do not fabricate return IDs.

		actions:
			start_return: @actions.initiate_return
				description: "Start a return"
				with order_id = ...
				with reason = ...
				set @variables.case_id = @outputs.return_id

			back: @utils.transition to @topic.topic_selector
				description: "Route to a different topic"

	after_reasoning:
		if @variables.case_id != "":
			transition to @topic.confirmation

topic general_support:
	label: "General Support"
	description: "Handle general support questions"
	reasoning:
		instructions: |
			Help the customer with general questions.
			If the question is about orders or returns, route appropriately.
		actions:
			escalate_now: @utils.escalate
				description: "Transfer to human agent"
			back: @utils.transition to @topic.topic_selector
				description: "Route to a different topic"

topic confirmation:
	label: "Confirmation"
	description: "Confirm the completed action"
	reasoning:
		instructions: ->
			| Your request has been processed. Reference: {!@variables.case_id}
			| Is there anything else I can help with?
		actions:
			new_request: @utils.transition to @topic.topic_selector
				description: "Start a new request"
			end_chat: @actions.end_conversation
				description: "End the conversation"
```
