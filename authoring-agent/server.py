"""FastAPI server for the ADLC Authoring Agent."""

from pathlib import Path

from harness import create_app
from agent import create_agent

_HERE = Path(__file__).parent

app = create_app(create_agent, {
    "agent_name": "ADLC Authoring Agent",
    "subagent_name": "ADLC Worker",
    "sessions_dir": _HERE / "sessions",
    "title": "Agentforce ADLC",
    "starter_prompts": [
        {
            "title": "Build a support agent",
            "prompt": "Build an Agentforce agent that handles customer support cases — it should look up case status, escalate to a human when needed, and search the knowledge base.",
        },
        {
            "title": "Discover org targets",
            "prompt": "Check which action targets (Flows, Apex, Retrievers) already exist in the MyOrg org so I know what to reuse.",
        },
        {
            "title": "Deploy an agent",
            "prompt": "Deploy the FAQBot agent bundle to MyOrg, publish it, and activate it.",
        },
        {
            "title": "Optimize from traces",
            "prompt": "Pull the last 24 hours of session traces for FAQBot, identify the top failure patterns, and propose fixes to the .agent file.",
        },
    ],
})

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
