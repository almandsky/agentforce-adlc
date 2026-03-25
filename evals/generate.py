"""
Conversational eval harness — drives the ADLC Authoring Agent against a
simulated user.

The authoring agent comes from ``authoring-agent/agent.py:create_agent()``
(same factory the CLI and FastAPI server use), sandboxed via
``harness.apply_sandbox``.  Instead of a human at ``input()``, a small
Anthropic-API-backed role-player supplies the user side of the dialogue.

Per-test output layout:
    <output_dir>/<test_id>/
    ├── sandbox/             # authoring agent's writable workspace
    │   └── …/<Name>.agent   # generated file (glob-discovered)
    ├── transcript.jsonl     # symlink → SDK's native jsonl
    ├── activity.log         # tool-call trace (print_activity format)
    └── conversation.log     # user ↔ agent text exchange
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic
import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)
from harness import apply_sandbox, link_transcript, print_activity

REPO_ROOT = Path(__file__).resolve().parents[1]
_AUTHORING_AGENT_DIR = str(REPO_ROOT / "authoring-agent")
if _AUTHORING_AGENT_DIR not in sys.path:
    sys.path.insert(0, _AUTHORING_AGENT_DIR)
from agent import create_agent  # noqa: E402


# --------------------------------------------------------------------------- #
#  Simulated user
# --------------------------------------------------------------------------- #

SIM_USER_SYSTEM = """\
You are role-playing a product manager asking an AI developer to build a
Salesforce Agentforce agent for you.

## Your goal
{goal}

## How to behave
- Open with a clear request describing what you want.
- Answer clarifying questions concisely (1-3 sentences). Invent reasonable
  details if the developer asks for specifics your goal doesn't cover.
- When the developer says the .agent file is written/complete, reply with
  exactly: DONE
- Don't volunteer extra scope — stick to your goal.
- You are the user, not the assistant. Never write code yourself.
"""


class SimulatedUser:
    """LLM-backed stand-in for the human side of the authoring dialogue."""

    def __init__(self, goal: str, model: str = "claude-haiku-4-5"):
        self.client = anthropic.Anthropic()
        self.model = model
        self.system = SIM_USER_SYSTEM.format(goal=goal)
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


# --------------------------------------------------------------------------- #
#  Generation
# --------------------------------------------------------------------------- #


@dataclass
class GenerateResult:
    test_id: str
    agent_content: Optional[str]
    agent_file: Optional[Path]
    transcript_path: Optional[Path]
    session_id: Optional[str]
    num_turns: int = 0
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    error: Optional[str] = None
    conversation: list[tuple[str, str]] = field(default_factory=list)


def _find_agent_file(sandbox: Path) -> Optional[Path]:
    hits = list(sandbox.rglob("*.agent"))
    return min(hits, key=lambda p: len(p.parts)) if hits else None


def _extract_text(msg: AssistantMessage) -> str:
    return "\n".join(
        b.text for b in msg.content if isinstance(b, TextBlock)
    ).strip()


async def _run_conversation(
    goal: str,
    test_id: str,
    output_dir: Path,
    max_turns: int,
    sim_model: str,
    verbose: bool,
) -> GenerateResult:
    test_dir = output_dir / test_id
    sandbox = test_dir / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.pop("CLAUDECODE", None)

    options = apply_sandbox(create_agent(), sandbox)
    options.env = env
    options.permission_mode = "bypassPermissions"

    sim = SimulatedUser(goal, model=sim_model)
    result = GenerateResult(
        test_id=test_id, agent_content=None, agent_file=None,
        transcript_path=None, session_id=None,
    )
    activity: list[str] = []

    def log_activity(msg):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_activity(msg, flush=False)
        text = buf.getvalue()
        if text:
            activity.append(text.rstrip("\n"))
            if verbose:
                print(text, end="", flush=True)

    try:
        async with ClaudeSDKClient(options) as client:
            user_msg = sim.opening()
            result.conversation.append(("user", user_msg))
            if verbose:
                print(f"\n[user] {user_msg}\n")

            for _ in range(max_turns):
                await client.query(user_msg)
                agent_text = ""

                async for msg in client.receive_response():
                    log_activity(msg)
                    if isinstance(msg, AssistantMessage):
                        t = _extract_text(msg)
                        if t:
                            agent_text = t
                    elif isinstance(msg, ResultMessage):
                        if not result.session_id and msg.session_id:
                            result.session_id = msg.session_id
                            link_transcript(
                                msg.session_id, test_dir,
                                Path(options.cwd or REPO_ROOT),
                            )
                        result.num_turns += msg.num_turns or 0
                        result.duration_ms += msg.duration_ms or 0
                        if msg.total_cost_usd:
                            result.total_cost_usd += msg.total_cost_usd
                        if msg.is_error:
                            result.error = str(msg.result)

                result.conversation.append(("agent", agent_text))

                if result.error or _find_agent_file(sandbox):
                    break

                user_msg = sim.reply(agent_text)
                result.conversation.append(("user", user_msg))
                if verbose:
                    print(f"\n[user] {user_msg}\n")
                if user_msg.strip().upper() == "DONE":
                    break

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"

    # Persist logs
    (test_dir / "activity.log").write_text("\n".join(activity) + "\n")
    (test_dir / "conversation.log").write_text(
        "\n\n".join(f"[{who}]\n{what}" for who, what in result.conversation) + "\n"
    )
    if result.session_id:
        result.transcript_path = test_dir / "transcript.jsonl"
        if not result.transcript_path.exists():
            result.transcript_path = None

    agent_file = _find_agent_file(sandbox)
    if agent_file:
        result.agent_file = agent_file
        result.agent_content = agent_file.read_text()
    elif not result.error:
        result.error = "no .agent file produced"

    return result


def generate_agent(
    prompt: str,
    test_id: str,
    output_dir: Path,
    max_turns: int = 6,
    sim_model: str = "claude-haiku-4-5",
    verbose: bool = False,
) -> GenerateResult:
    """Sync entry point for the conversational generation loop."""
    return anyio.run(
        _run_conversation, prompt, test_id, output_dir,
        max_turns, sim_model, verbose,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run one conversational eval")
    p.add_argument("prompt", help="The simulated user's goal")
    p.add_argument("--test-id", default="adhoc")
    p.add_argument("--output-dir", default="evals/results/generated")
    p.add_argument("--max-turns", type=int, default=6)
    p.add_argument("--sim-model", default="claude-haiku-4-5")
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args()

    r = generate_agent(
        args.prompt, args.test_id, Path(args.output_dir),
        max_turns=args.max_turns, sim_model=args.sim_model,
        verbose=not args.quiet,
    )

    print(f"\n--- {r.test_id} ---")
    print(f"session:    {r.session_id}")
    print(f"turns:      {r.num_turns} (conv: {len(r.conversation)} msgs)")
    print(f"cost:       ${r.total_cost_usd:.4f}")
    print(f"agent file: {r.agent_file}")
    print(f"transcript: {r.transcript_path}")
    if r.error:
        print(f"error:      {r.error}")
