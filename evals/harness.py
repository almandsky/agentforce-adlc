"""
Conversational eval harness — drives the ADLC Authoring Agent against a
simulated user.

Uses the claude_code system-prompt preset so the agent sees the same
CLAUDE.md and skills a real user would. A small Anthropic-API-backed
role-player supplies the user side of the dialogue instead of a human
at ``input()``.

Each test runs in an isolated scratch workspace seeded with just the
files the authoring agent needs (sfdx-project.json, .claude/, CLAUDE.md).
The workspace starts with an empty bundles dir, so whatever .agent file
appears IS the output — no before/after diffing.

Per-test artifacts (tailable while running):
    <output_dir>/<test_id>/
    ├── workspace/           # isolated cwd for the authoring agent
    │   └── force-app/.../aiAuthoringBundles/<Name>/<Name>.agent
    ├── transcript.jsonl     # symlink → SDK's native jsonl
    ├── activity.log         # tool-call trace
    └── conversation.log     # user ↔ agent text exchange
"""

import contextlib
import io
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLES_REL = Path("force-app") / "main" / "default" / "aiAuthoringBundles"

DEFAULT_SIM_MODEL = "claude-haiku-4-5"
DEFAULT_MAX_TURNS = 6

# Allow the SDK to spawn from inside a Claude Code session.
for _var in ("CLAUDECODE", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_ENTRYPOINT"):
    os.environ.pop(_var, None)


# ─── Simulated user ──────────────────────────────────────────────────────

# TODO: add potential profiles / personas for the sim user (e.g. more/less technical, more/less verbose)
SIM_USER_SYSTEM = """\
You are role-playing a Salesforce administrator asking an AI developer to build a
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

    def __init__(self, prompt: str, goal: str | None = None,
                 model: str = DEFAULT_SIM_MODEL):
        self.client = anthropic.Anthropic()
        self.model = model
        self.system = SIM_USER_SYSTEM.format(prompt=prompt, goal=goal or DEFAULT_GOAL)
        self.history: list[dict] = []

    def opening(self) -> str:
        return self._turn("<begin the conversation by stating your request>")

    def reply(self, agent_said: str) -> str:
        return self._turn(agent_said)

    def _turn(self, agent_said: str) -> str:
        self.history.append({"role": "user", "content": agent_said})
        resp = self.client.messages.create(
            model=self.model, max_tokens=500,
            system=self.system, messages=self.history,  # type: ignore[arg-type]
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        self.history.append({"role": "assistant", "content": text})
        return text


# ─── Activity log formatting ─────────────────────────────────────────────

_tool_use_cache: dict[str, str] = {}


def _format_tool_input(tool_name: str, input_data: dict) -> str:
    if tool_name == "Task":
        desc = input_data.get("description", "")
        return f'"{desc}"' if desc else ""
    if tool_name in ("Read", "Write", "Edit"):
        path = input_data.get("file_path", "")
        return path.split("/")[-1] if path else ""
    if tool_name in ("Glob", "Grep"):
        return input_data.get("pattern", "")[:40]
    if tool_name == "Bash":
        cmd = input_data.get("command", "")
        return cmd[:50] + "..." if len(cmd) > 50 else cmd
    if tool_name == "WebSearch":
        return input_data.get("query", "")[:40]
    if tool_name == "WebFetch":
        url = input_data.get("url", "")
        return url[:50] + "..." if len(url) > 50 else url
    if tool_name == "TodoWrite":
        todos = input_data.get("todos", [])
        lines = []
        for i, todo in enumerate(todos):
            marker = {"completed": "+", "in_progress": "*"}.get(todo["status"], "-")
            lines.append(f"{marker} {i + 1}. {todo['content']}")
        return "\n".join(lines)
    return ""


def _format_tool_result(tool_name: str, content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return ""
        lines = text.split("\n")
        if tool_name == "Glob":
            return f"{len(lines)} file(s)"
        if tool_name == "Grep":
            return f"{len(lines)} match(es)"
        if tool_name == "Read":
            return f"{len(lines)} lines"
        if tool_name == "Bash":
            return text if len(lines) == 1 and len(text) < 60 else f"{len(lines)} lines"
        if tool_name in ("WebSearch", "WebFetch"):
            return f"{len(text)} chars"
        first = lines[0][:60]
        return first + "..." if len(lines) > 1 or len(lines[0]) > 60 else first
    if isinstance(content, list):
        parts = [getattr(i, "text", i.get("text") if isinstance(i, dict) else None)
                 for i in content]
        parts = [p for p in parts if p]
        if parts:
            combined = " ".join(parts)
            return combined[:60] + "..." if len(combined) > 60 else combined
        return f"{len(content)} item(s)"
    return str(content)[:60]


def print_activity(msg, file=None) -> None:
    """Print a human-readable trace line for one SDK message."""
    def out(s): print(s, file=file, flush=True)

    if isinstance(msg, AssistantMessage):
        p = "  [subagent] " if msg.parent_tool_use_id else ""
        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                _tool_use_cache[block.id] = block.name
                detail = _format_tool_input(block.name, block.input)
                out(f"{p}-> {block.name}: {detail}" if detail else f"{p}-> {block.name}")
            elif isinstance(block, TextBlock):
                for line in block.text.strip().split("\n"):
                    if line:
                        out(f"{p}{line}")
            elif isinstance(block, ThinkingBlock):
                out(f"{p}(thinking...)")
            elif isinstance(block, ToolResultBlock):
                out(f"{p}<- tool result [{'error' if block.is_error else 'ok'}]")

    elif isinstance(msg, UserMessage):
        p = "  [subagent] " if msg.parent_tool_use_id else ""
        if isinstance(msg.content, str):
            out(f"{p}[user input received]")
        else:
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    name = _tool_use_cache.pop(block.tool_use_id, "")
                    mark = "x" if block.is_error else "+"
                    summary = _format_tool_result(name, block.content)
                    if block.is_error:
                        out(f"{p}<- {mark} {name} error: {summary}")
                    elif summary:
                        out(f"{p}<- {mark} {name}: {summary}")

    elif isinstance(msg, ResultMessage):
        out(f"\n{'=' * 50}")
        out(f"Completed in {msg.duration_ms / 1000:.1f}s ({msg.num_turns} turns)")
        if msg.total_cost_usd:
            out(f"Cost: ${msg.total_cost_usd:.4f}")
        if msg.is_error:
            out(f"Error: {msg.result}")
        out(f"{'=' * 50}\n")


def _link_transcript(session_id: str, dest_dir: Path, cwd: Path) -> None:
    """Symlink the SDK's native transcript.jsonl into dest_dir."""
    mangled = str(cwd.resolve()).replace("/", "-")
    src = Path.home() / ".claude" / "projects" / mangled / f"{session_id}.jsonl"
    link = dest_dir / "transcript.jsonl"
    if src.exists() and not link.exists():
        link.symlink_to(src)


# ─── Conversation loop ───────────────────────────────────────────────────

EVAL_ISOLATION = """

## Eval isolation — IMPORTANT
You are running inside an evaluation harness with a fresh workspace.
Author the agent FROM SCRATCH based only on the user's requirements and
the adlc-author skill reference docs. Write your bundle under
force-app/main/default/aiAuthoringBundles/ as usual.
"""


@dataclass
class GenerateResult:
    test_id: str
    agent_content: Optional[str] = None
    agent_file: Optional[Path] = None
    transcript_path: Optional[Path] = None
    session_id: Optional[str] = None
    num_turns: int = 0
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    error: Optional[str] = None
    conversation: list[tuple[str, str]] = field(default_factory=list)


def default_output_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return REPO_ROOT / "evals" / "results" / f"run-{ts}"


def _make_workspace(test_dir: Path) -> Path:
    """Create an isolated sfdx workspace under test_dir, seeded with just
    enough for the authoring agent to run (skills, project config)."""
    ws = test_dir / "workspace"
    if ws.exists():
        shutil.rmtree(ws)
    (ws / BUNDLES_REL).mkdir(parents=True)
    shutil.copy(REPO_ROOT / "sfdx-project.json", ws / "sfdx-project.json")
    for name in (".claude", "CLAUDE.md"):
        src = REPO_ROOT / name
        if src.exists():
            (ws / name).symlink_to(src)
    return ws


def _find_agent(workspace: Path) -> Optional[Path]:
    found = list((workspace / BUNDLES_REL).rglob("*.agent"))
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def _extract_text(msg: AssistantMessage) -> str:
    return "\n".join(b.text for b in msg.content if isinstance(b, TextBlock)).strip()


async def _run_conversation(
    prompt: str, test_id: str, output_dir: Path,
    max_turns: int, sim_model: str, verbose: bool, goal: Optional[str],
) -> GenerateResult:
    test_dir = output_dir / test_id
    test_dir.mkdir(parents=True, exist_ok=True)
    workspace = _make_workspace(test_dir)

    options = ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code", "append": EVAL_ISOLATION},
        model="claude-opus-4-6",
        cwd=str(workspace),
        setting_sources=["project"],
        max_thinking_tokens=3000,
        max_turns=30,
        permission_mode="bypassPermissions",
    )

    # If the eval provides a goal, the sim user drives termination via DONE.
    # Otherwise exit fast on first file write.
    stop_on_file = goal is None

    sim = SimulatedUser(prompt, goal=goal, model=sim_model)
    result = GenerateResult(test_id=test_id)

    activity_log = (test_dir / "activity.log").open("w", buffering=1)
    conv_log = (test_dir / "conversation.log").open("w", buffering=1)

    def log_activity(msg):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_activity(msg)
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
                            _link_transcript(msg.session_id, test_dir, workspace)
                        result.num_turns += msg.num_turns or 0
                        result.duration_ms += msg.duration_ms or 0
                        if msg.total_cost_usd:
                            result.total_cost_usd += msg.total_cost_usd
                        if msg.is_error:
                            result.error = str(msg.result)

                conv_log.write("\n")
                agent_text = "\n".join(agent_chunks)
                result.conversation.append(("agent", agent_text))

                if result.error or (stop_on_file and _find_agent(workspace)):
                    break

                user_msg = sim.reply(agent_text)
                log_conv("user", user_msg)
                if user_msg.strip().upper().endswith("DONE"):
                    break
            else:
                activity_log.write("Conversation ended due to max turns.\n")

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
    finally:
        activity_log.close()
        conv_log.close()

    if result.session_id:
        link = test_dir / "transcript.jsonl"
        result.transcript_path = link if link.exists() else None

    agent_file = _find_agent(workspace)
    if agent_file:
        result.agent_file = agent_file
        result.agent_content = agent_file.read_text()
    elif not result.error:
        result.error = "no .agent file produced"

    return result


def simulate_conversation(
    prompt: str, test_id: str, output_dir: Path,
    goal: Optional[str] = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    sim_model: str = DEFAULT_SIM_MODEL,
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
    p.add_argument("--goal", help="Sim user's success criteria / follow-up script. "
                                  "If set, the loop won't stop on first file write.")
    p.add_argument("--test-id", default="adhoc")
    p.add_argument("--output-dir", help="Log dir (default: evals/results/run-<ts>)")
    p.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    p.add_argument("--sim-model", default=DEFAULT_SIM_MODEL)
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    print(f"Logs: {out_dir}/{args.test_id}/")

    r = simulate_conversation(
        args.prompt, args.test_id, out_dir, goal=args.goal,
        max_turns=args.max_turns, sim_model=args.sim_model, verbose=not args.quiet,
    )

    print(f"\n--- {r.test_id} ---")
    print(f"session:    {r.session_id}")
    print(f"turns:      {r.num_turns} (conv: {len(r.conversation)} msgs)")
    print(f"cost:       ${r.total_cost_usd:.4f}")
    print(f"agent file: {r.agent_file}")
    print(f"transcript: {r.transcript_path}")
    if r.error:
        print(f"error:      {r.error}")
