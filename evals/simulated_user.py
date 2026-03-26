"""
LLM-backed stand-in for the human side of the authoring dialogue.

A small Anthropic-API-backed role-player that supplies the user side of the
conversation instead of a human at ``input()``.
"""

import anthropic

SIM_USER_SYSTEM = """\
You are role-playing a product manager asking an AI developer to build a
Salesforce Agentforce agent for you.

## Your request
{prompt}

## When you're done
{goal}

## How to behave
- Open with a clear request describing what you want.
- Answer clarifying questions concisely (1-3 sentences). Invent reasonable
  details if the developer asks for specifics your request doesn't cover.
- Don't volunteer extra scope — stick to your request.
- You are the user, not the assistant. Never write code yourself.
"""

DEFAULT_GOAL = (
    "Once the developer confirms the .agent file is written and complete, "
    "reply with exactly: DONE"
)


class SimulatedUser:
    """LLM-backed stand-in for the human side of the authoring dialogue."""

    def __init__(
        self,
        prompt: str,
        goal: str | None = None,
        model: str = "claude-haiku-4-5",
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.system = SIM_USER_SYSTEM.format(
            prompt=prompt, goal=goal or DEFAULT_GOAL
        )
        self.history: list[dict] = []

    def opening(self) -> str:
        """First message — kicks off the conversation."""
        return self._turn("<begin the conversation by stating your request>")

    def reply(self, agent_said: str) -> str:
        """Respond to whatever the authoring agent just said."""
        return self._turn(agent_said)

    def _turn(self, agent_said: str) -> str:
        self.history.append({"role": "user", "content": agent_said})
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=self.system,
            messages=self.history,  # type: ignore[arg-type]
        )
        text = "".join(
            b.text for b in resp.content if b.type == "text"
        ).strip()
        self.history.append({"role": "assistant", "content": text})
        return text
