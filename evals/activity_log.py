"""Console-style activity tracer for SDK messages.

Formats tool calls, results, and assistant text into a tailable log.
Also handles symlinking the SDK's native transcript.jsonl into a
per-test output directory.
"""

from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    UserMessage,
    ResultMessage,
    ToolUseBlock,
    ToolResultBlock,
    TextBlock,
    ThinkingBlock,
)


# --------------------------------------------------------------------------- #
#  Transcript linking
# --------------------------------------------------------------------------- #

def link_transcript(session_id: str, dest_dir: Path, cwd: Path) -> Path | None:
    """Symlink the SDK's native transcript.jsonl into dest_dir.

    The SDK stores transcripts at ~/.claude/projects/<mangled-cwd>/<session>.jsonl
    where <mangled-cwd> is the absolute cwd with '/' replaced by '-'.
    """
    mangled = str(cwd.resolve()).replace("/", "-")
    transcript = Path.home() / ".claude" / "projects" / mangled / f"{session_id}.jsonl"
    if not transcript.exists():
        return None
    link_path = dest_dir / "transcript.jsonl"
    if not link_path.exists():
        link_path.symlink_to(transcript)
    return link_path


# --------------------------------------------------------------------------- #
#  Activity formatting
# --------------------------------------------------------------------------- #

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
        elif tool_name == "Grep":
            return f"{len(lines)} match(es)"
        elif tool_name == "Read":
            return f"{len(lines)} lines"
        elif tool_name == "Bash":
            if len(lines) == 1 and len(text) < 60:
                return text
            return f"{len(lines)} lines"
        elif tool_name in ("WebSearch", "WebFetch"):
            return f"{len(text)} chars"
        first_line = lines[0][:60]
        if len(lines) > 1 or len(lines[0]) > 60:
            first_line += "..."
        return first_line
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if hasattr(item, "text"):
                text_parts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                text_parts.append(item["text"])
        if text_parts:
            combined = " ".join(text_parts)
            return combined[:60] + "..." if len(combined) > 60 else combined
        return f"{len(content)} item(s)"
    return str(content)[:60]


def _format_tool_input(tool_name: str, input_data: dict) -> str:
    if tool_name == "Task":
        desc = input_data.get("description", "")
        return f'"{desc}"' if desc else ""
    elif tool_name in ("Read", "Write", "Edit"):
        path = input_data.get("file_path", "")
        return path.split("/")[-1] if path else ""
    elif tool_name in ("Glob", "Grep"):
        return input_data.get("pattern", "")[:40]
    elif tool_name == "Bash":
        cmd = input_data.get("command", "")
        return cmd[:50] + "..." if len(cmd) > 50 else cmd
    elif tool_name == "WebSearch":
        return input_data.get("query", "")[:40]
    elif tool_name == "WebFetch":
        url = input_data.get("url", "")
        return url[:50] + "..." if len(url) > 50 else url
    elif tool_name == "TodoWrite":
        todos = input_data.get("todos", [])
        lines = []
        for i, todo in enumerate(todos):
            marker = "+" if todo["status"] == "completed" else \
                     "*" if todo["status"] == "in_progress" else "-"
            lines.append(f"{marker} {i + 1}. {todo['content']}")
        return "\n".join(lines) if lines else ""
    return ""


_tool_use_cache: dict[str, str] = {}


def _prefix(parent_tool_use_id: str | None) -> str:
    return "  [subagent] " if parent_tool_use_id else ""


def print_activity(msg, flush: bool = True) -> None:
    """Print a human-readable trace line for one SDK message."""

    if isinstance(msg, AssistantMessage):
        p = _prefix(msg.parent_tool_use_id)
        for block in msg.content:
            if isinstance(block, ToolUseBlock):
                _tool_use_cache[block.id] = block.name
                detail = _format_tool_input(block.name, block.input)
                print(f"{p}-> {block.name}: {detail}" if detail else f"{p}-> {block.name}", flush=flush)
            elif isinstance(block, TextBlock):
                text = block.text.strip()
                if text:
                    for line in text.split("\n"):
                        print(f"{p}{line}", flush=flush)
            elif isinstance(block, ThinkingBlock):
                print(f"{p}(thinking...)", flush=flush)
            elif isinstance(block, ToolResultBlock):
                status = "error" if block.is_error else "ok"
                print(f"{p}<- tool result [{status}]", flush=flush)

    elif isinstance(msg, UserMessage):
        p = _prefix(msg.parent_tool_use_id)
        if isinstance(msg.content, str):
            print(f"{p}[user input received]", flush=flush)
        else:
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    tool_name = _tool_use_cache.pop(block.tool_use_id, "")
                    status = "x" if block.is_error else "+"
                    summary = _format_tool_result(tool_name, block.content)
                    if block.is_error:
                        print(f"{p}<- {status} {tool_name} error: {summary}", flush=flush)
                    elif summary:
                        print(f"{p}<- {status} {tool_name}: {summary}", flush=flush)

    elif isinstance(msg, ResultMessage):
        print(f"\n{'=' * 50}", flush=flush)
        print(f"Completed in {msg.duration_ms / 1000:.1f}s ({msg.num_turns} turns)", flush=flush)
        if msg.total_cost_usd:
            print(f"Cost: ${msg.total_cost_usd:.4f}", flush=flush)
        if msg.is_error:
            print(f"Error: {msg.result}", flush=flush)
        print(f"{'=' * 50}\n", flush=flush)
