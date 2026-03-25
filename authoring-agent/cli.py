"""CLI entry point for the ADLC Authoring Agent."""

from pathlib import Path

from harness import run_cli
from agent import create_agent

_HERE = Path(__file__).parent


def main() -> None:
    sandbox = _HERE / "sessions" / "cli-sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    run_cli(
        create_agent,
        agent_name="ADLC Authoring Agent",
        sandbox_path=sandbox,
    )


if __name__ == "__main__":
    main()
