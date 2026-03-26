"""
Conversational eval harness — drives the ADLC Authoring Agent against a
simulated user.

Uses the claude_code system-prompt preset so the agent sees the same
CLAUDE.md and skills a real user would. Instead of a human at
``input()``, a small Anthropic-API-backed role-player supplies the user
side of the dialogue.

Generated .agent files land in the repo's natural location:
    force-app/main/default/aiAuthoringBundles/<AgentName>/

Per-test logs (tailable while running):
    <output_dir>/<test_id>/
    ├── transcript.jsonl     # symlink → SDK's native jsonl
    ├── activity.log         # tool-call trace (print_activity format)
    └── conversation.log     # user ↔ agent text exchange
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ClaudeAgentOptions,
)
from activity_log import link_transcript, print_activity
from simulated_user import SimulatedUser

REPO_ROOT = Path(__file__).resolve().parents[1]


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


BUNDLES_DIR = REPO_ROOT / "force-app" / "main" / "default" / "aiAuthoringBundles"


def default_output_dir() -> Path:
    """Timestamped results dir so re-runs don't clobber prior logs."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return REPO_ROOT / "evals" / "results" / f"run-{ts}"


EVAL_ISOLATION = """

## Eval isolation — IMPORTANT
You are running inside an evaluation harness. Author the agent FROM
SCRATCH based only on the user's requirements and the adlc-author skill
reference docs. Do NOT:
- read, glob, or grep existing .agent files under force-app/ or evals/
- look at evals/ at all (that is the harness, not your workspace)
- copy or adapt a previously-generated agent

Writing your new agent bundle under force-app/main/default/aiAuthoringBundles/
is fine — just don't read what's already there.
"""


def _snapshot_bundles() -> set[Path]:
    return set(BUNDLES_DIR.rglob("*.agent")) if BUNDLES_DIR.exists() else set()


def _find_new_agent(before: set[Path]) -> Optional[Path]:
    new = _snapshot_bundles() - before
    return max(new, key=lambda p: p.stat().st_mtime) if new else None


def _extract_text(msg: AssistantMessage) -> str:
    return "\n".join(
        b.text for b in msg.content if isinstance(b, TextBlock)
    ).strip()


async def _run_conversation(
    prompt: str,
    test_id: str,
    output_dir: Path,
    max_turns: int,
    sim_model: str,
    verbose: bool,
    goal: Optional[str],
) -> GenerateResult:
    test_dir = output_dir / test_id
    test_dir.mkdir(parents=True, exist_ok=True)

    # Invoke claude code that matches what users likely have by default
    options = ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code", "append": EVAL_ISOLATION}, # need to append on the isolation instructions so we get claude code system prompt + claude.md plus the eval isolation instructions all together
        model="claude-opus-4-6", # likely model users have by default in claude code
        cwd=str(REPO_ROOT),
        setting_sources=["project"],
        max_thinking_tokens=3000,
        max_turns=30,
        permission_mode = "bypassPermissions"
    )

    # Get a snapshot of the agents that exist already so we can detect if a new one gets created during the conversation.
    before = _snapshot_bundles()
    # If the eval provides a custom goal, the sim user drives termination via DONE.
    # Otherwise, exit fast on first file write.
    stop_on_file = goal is None

    # Create a simulated user
    sim = SimulatedUser(prompt, goal=goal, model=sim_model)
    result = GenerateResult(
        test_id=test_id, agent_content=None, agent_file=None,
        transcript_path=None, session_id=None,
    )

    # Set up logs for this test run
    activity_log = (test_dir / "activity.log").open("w", buffering=1)
    conv_log = (test_dir / "conversation.log").open("w", buffering=1)

    def log_activity(msg):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_activity(msg, flush=False)
        text = buf.getvalue()
        if text:
            activity_log.write(text)
            if verbose:
                print(text, end="", flush=True)

    def log_conv(who: str, what: str):
        result.conversation.append((who, what))
        conv_log.write(f"[{who}]\n{what}\n\n")
        if who == "user":
            activity_log.write(f"\n{'=' * 50}\n[user]\n{what}\n{'=' * 50}\n\n")
            if verbose:
                print(f"\n[user] {what}\n")

    try:
        async with ClaudeSDKClient(options) as client:
            user_msg = sim.opening()
            log_conv("user", user_msg)

            for _ in range(max_turns):
                await client.query(user_msg)
                agent_chunks: list[str] = []
                conv_log.write("[agent]\n")

                async for msg in client.receive_response():
                    log_activity(msg)
                    if isinstance(msg, AssistantMessage):
                        t = _extract_text(msg)
                        if t:
                            conv_log.write(t + "\n")
                            agent_chunks.append(t)
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

                conv_log.write("\n")
                agent_text = "\n".join(agent_chunks)
                result.conversation.append(("agent", agent_text))

                if result.error or (stop_on_file and _find_new_agent(before)):
                    break

                user_msg = sim.reply(agent_text)
                log_conv("user", user_msg)
                if user_msg.strip().upper() == "DONE":
                    break
            else:
                activity_log.write("Conversation ended due to max turns.\n")

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
    finally:
        activity_log.close()
        conv_log.close()
    if result.session_id:
        result.transcript_path = test_dir / "transcript.jsonl"
        if not result.transcript_path.exists():
            result.transcript_path = None

    agent_file = _find_new_agent(before)
    if agent_file:
        result.agent_file = agent_file
        result.agent_content = agent_file.read_text()
    elif not result.error:
        result.error = "no .agent file produced"

    return result


def simulate_conversation(
    prompt: str,
    test_id: str,
    output_dir: Path,
    goal: Optional[str] = None,
    max_turns: int = 6,
    sim_model: str = "claude-haiku-4-5",
    verbose: bool = False,
) -> GenerateResult:
    """Sync entry point for the conversational generation loop.

    If ``goal`` is provided, the simulated user drives termination (the
    harness will NOT stop on first file write). If omitted, the loop
    exits as soon as a .agent file appears.
    """
    return anyio.run(
        _run_conversation, prompt, test_id, output_dir,
        max_turns, sim_model, verbose, goal,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run one conversational eval")
    p.add_argument("prompt", help="The simulated user's request")
    p.add_argument("--goal", default=None,
                   help="Sim user's success criteria / follow-up script. "
                        "If set, the loop won't stop on first file write.")
    p.add_argument("--test-id", default="adhoc")
    p.add_argument("--output-dir", default=None,
                   help="Log output dir (default: evals/results/run-<timestamp>)")
    p.add_argument("--max-turns", type=int, default=6)
    p.add_argument("--sim-model", default="claude-haiku-4-5")
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    print(f"Logs: {out_dir}/{args.test_id}/")

    r = simulate_conversation(
        args.prompt, args.test_id, out_dir,
        goal=args.goal, max_turns=args.max_turns,
        sim_model=args.sim_model, verbose=not args.quiet,
    )

    print(f"\n--- {r.test_id} ---")
    print(f"session:    {r.session_id}")
    print(f"turns:      {r.num_turns} (conv: {len(r.conversation)} msgs)")
    print(f"cost:       ${r.total_cost_usd:.4f}")
    print(f"agent file: {r.agent_file}")
    print(f"transcript: {r.transcript_path}")
    if r.error:
        print(f"error:      {r.error}")
