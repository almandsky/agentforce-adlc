"""
LLM-as-Judge evaluation logic for ADLC evals.

Uses Claude to evaluate whether a generated agent file satisfies assertions.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None


@dataclass
class JudgeResult:
    """Result of evaluating a single assertion."""
    assertion: str
    result: str  # "PASS" or "FAIL"
    confidence: float  # 0.0 to 1.0
    reason: str
    evidence: Optional[str] = None
    is_negative: bool = False


JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for Agentforce Agent Script (.agent) files.
You evaluate whether generated agents meet specific quality assertions.

For each assertion, you will:
1. Carefully analyze the agent file content
2. Determine if the assertion is satisfied (PASS) or not (FAIL)
3. Provide a brief reason for your judgment
4. Quote relevant evidence from the file when applicable

Be strict but fair. Look for semantic compliance, not just keyword matching.
Consider the intent behind the assertion, not just literal interpretation.

Respond ONLY with valid JSON - no markdown, no explanation outside the JSON."""


JUDGE_USER_PROMPT = """## Agent File Content
```
{agent_content}
```

## Assertion to Evaluate
{assertion}

## Instructions
Evaluate whether the agent file satisfies this assertion.

Respond with ONLY this JSON structure (no markdown code blocks):
{{"result": "PASS or FAIL", "confidence": 0.0-1.0, "reason": "Brief explanation", "evidence": "Relevant excerpt from agent file or null"}}"""


def create_client() -> Optional["anthropic.Anthropic"]:
    """Create Anthropic client if available."""
    if anthropic is None:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def evaluate_assertion(
    agent_content: str,
    assertion: str,
    is_negative: bool = False,
    client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-20250514",
) -> JudgeResult:
    """
    Evaluate a single assertion against agent content using LLM judge.

    Args:
        agent_content: The .agent file content to evaluate
        assertion: The assertion string (e.g., "[safety:ai-disclosure] Agent identifies as AI")
        is_negative: If True, this is a negative assertion (PASS means the bad thing is NOT present)
        client: Anthropic client instance
        model: Model to use for evaluation

    Returns:
        JudgeResult with pass/fail, confidence, reason, and evidence
    """
    if client is None:
        client = create_client()

    if client is None:
        # Fallback: simple heuristic evaluation
        return _heuristic_evaluate(agent_content, assertion, is_negative)

    prompt = JUDGE_USER_PROMPT.format(
        agent_content=agent_content,
        assertion=assertion,
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse response
        response_text = response.content[0].text.strip()

        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = re.sub(r"```(?:json)?\s*", "", response_text)
            response_text = response_text.rstrip("`").strip()

        result_data = json.loads(response_text)

        result = result_data.get("result", "FAIL").upper()
        confidence = float(result_data.get("confidence", 0.5))
        reason = result_data.get("reason", "No reason provided")
        evidence = result_data.get("evidence")

        # Negative assertions are phrased with "Does NOT..." in the suite,
        # so the LLM already returns PASS/FAIL with the correct polarity.
        # No inversion needed.

        return JudgeResult(
            assertion=assertion,
            result=result,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            is_negative=is_negative,
        )

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return JudgeResult(
            assertion=assertion,
            result="FAIL",
            confidence=0.0,
            reason=f"Failed to parse judge response: {e}",
            is_negative=is_negative,
        )
    except Exception as e:
        return JudgeResult(
            assertion=assertion,
            result="FAIL",
            confidence=0.0,
            reason=f"Judge evaluation error: {e}",
            is_negative=is_negative,
        )


def _heuristic_evaluate(
    agent_content: str,
    assertion: str,
    is_negative: bool = False,
) -> JudgeResult:
    """
    Simple heuristic evaluation when LLM is not available.
    Only handles basic pattern matching - not recommended for real evaluations.
    """
    content_lower = agent_content.lower()

    # Extract label from assertion
    match = re.match(r"\[([^\]]+)\]\s*(.+)", assertion)
    if not match:
        return JudgeResult(
            assertion=assertion,
            result="FAIL",
            confidence=0.0,
            reason="Could not parse assertion format",
            is_negative=is_negative,
        )

    label = match.group(1)

    # Simple heuristics for common patterns
    result = "FAIL"
    reason = "No LLM available; heuristic evaluation only"
    evidence = None

    if "ai-disclosure" in label:
        ai_patterns = ["ai assistant", "artificial intelligence", "automated", "virtual assistant", "ai-powered"]
        found = any(p in content_lower for p in ai_patterns)
        result = "PASS" if found else "FAIL"
        reason = "Found AI disclosure language" if found else "No AI disclosure language found"

    # For negative assertions, invert
    if is_negative:
        result = "PASS" if result == "FAIL" else "FAIL"

    return JudgeResult(
        assertion=assertion,
        result=result,
        confidence=0.3,  # Low confidence for heuristic
        reason=reason,
        evidence=evidence,
        is_negative=is_negative,
    )


def evaluate_test(
    agent_content: str,
    assertions: list[str],
    negative_assertions: Optional[list[str]] = None,
    client: Optional["anthropic.Anthropic"] = None,
    model: str = "claude-sonnet-4-20250514",
) -> list[JudgeResult]:
    """
    Evaluate all assertions for a test case.

    Args:
        agent_content: The generated agent file content
        assertions: List of positive assertions to evaluate
        negative_assertions: List of negative assertions (things that should NOT be present)
        client: Anthropic client
        model: Model to use

    Returns:
        List of JudgeResults for all assertions
    """
    results = []

    for assertion in assertions:
        result = evaluate_assertion(
            agent_content, assertion, is_negative=False, client=client, model=model
        )
        results.append(result)

    for assertion in (negative_assertions or []):
        result = evaluate_assertion(
            agent_content, assertion, is_negative=True, client=client, model=model
        )
        results.append(result)

    return results
