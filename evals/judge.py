"""
LLM-as-Judge evaluation for ADLC evals.

Assertions are grouped by target artifact (the .agent file vs. the authoring
session transcript) and batched — one API call per artifact, not per assertion.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

from taxonomy import artifact_for_label, extract_label

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-20250514"


@dataclass
class JudgeResult:
    assertion: str
    result: str  # "PASS" or "FAIL"
    confidence: float
    reason: str
    evidence: Optional[str] = None


JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for Agentforce Agent Script authoring.

You will be shown an ARTIFACT (either the generated .agent file, or the
transcript of the authoring session that produced it) and asked to judge
a list of assertions against it.

For each assertion:
1. Analyze the artifact carefully
2. Determine PASS or FAIL
3. Give a brief reason
4. Quote relevant evidence when applicable

Be strict but fair. Look for semantic compliance, not just keyword matching.

Respond ONLY with a JSON array — one object per assertion, in the same order
as the input list. No markdown, no prose outside the JSON."""


ARTIFACT_HEADERS = {
    "agent": "## Generated .agent file",
    "process": "## Authoring session transcript\n"
               "(User ↔ agent conversation followed by tool-call activity log)",
}

JUDGE_USER_PROMPT = """{header}
```
{content}
```

## Assertions to Evaluate
{assertions}

## Instructions
Evaluate each assertion above against the artifact. Return a JSON array with
one object per assertion, IN THE SAME ORDER:

[
  {{"result": "PASS or FAIL", "confidence": 0.0-1.0, "reason": "...", "evidence": "... or null"}},
  ...
]

No markdown fences, no extra text — just the JSON array."""


def create_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set — required for LLM-as-judge evaluation"
        )
    return anthropic.Anthropic(api_key=api_key)


def _judge_batch(
    artifact_kind: str,
    artifact_text: Optional[str],
    assertions: list[str],
    client: anthropic.Anthropic,
    model: str,
) -> list[JudgeResult]:
    """One API call: evaluate all assertions targeting the same artifact."""

    def fail_all(reason: str) -> list[JudgeResult]:
        return [JudgeResult(assertion, "FAIL", 0.0, reason) for assertion in assertions]

    if not artifact_text:
        return fail_all(f"No '{artifact_kind}' artifact available")

    assertion_list = "\n".join(
        f"{n}. {assertion}" for n, assertion in enumerate(assertions, 1)
    )
    prompt = JUDGE_USER_PROMPT.format(
        header=ARTIFACT_HEADERS.get(artifact_kind, "## Artifact"),
        content=artifact_text,
        assertions=assertion_list,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=300 * len(assertions),
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        reply = response.content[0].text.strip()  # type: ignore[union-attr]
        if reply.startswith("```"):
            reply = re.sub(r"```(?:json)?\s*", "", reply).rstrip("`").strip()

        verdicts = json.loads(reply)
        if not isinstance(verdicts, list) or len(verdicts) != len(assertions):
            actual = len(verdicts) if isinstance(verdicts, list) else type(verdicts).__name__
            return fail_all(f"Judge returned {actual}, expected {len(assertions)} results")

        return [
            JudgeResult(
                assertion=assertion,
                result=str(verdict.get("result", "FAIL")).upper(),
                confidence=float(verdict.get("confidence", 0.5)),
                reason=verdict.get("reason", "No reason provided"),
                evidence=verdict.get("evidence"),
            )
            for assertion, verdict in zip(assertions, verdicts)
        ]

    except Exception as e:
        return fail_all(f"Judge error: {type(e).__name__}: {e}")


def evaluate_test(
    artifacts: dict[str, str],
    assertions: list[str],
    negative_assertions: Optional[list[str]] = None,
    client: Optional[anthropic.Anthropic] = None,
    model: str = DEFAULT_JUDGE_MODEL,
) -> list[JudgeResult]:
    """Evaluate all assertions for a test case.

    ``artifacts`` maps artifact kind → content:
      - "agent": the generated .agent file text
      - "process": concatenated conversation.log + activity.log

    Assertions are grouped by target artifact; one API call per group.
    """
    if client is None:
        client = create_client()

    all_assertions = list(assertions) + list(negative_assertions or [])

    by_artifact: dict[str, list[str]] = {}
    for assertion in all_assertions:
        artifact_kind = artifact_for_label(extract_label(assertion) or "")
        by_artifact.setdefault(artifact_kind, []).append(assertion)

    results: list[JudgeResult] = []
    for artifact_kind, batch in by_artifact.items():
        artifact_text = artifacts.get(artifact_kind)
        results.extend(_judge_batch(artifact_kind, artifact_text, batch, client, model))
    return results
