"""
Per-skill evaluation dimensions and weighted scoring for ADLC evals.

Labels from taxonomy.py map to dimensions automatically via prefix matching.
Each skill has weighted dimensions that roll up into an overall skill score.
"""

import fnmatch
from typing import Optional


# Skill rubrics — weighted dimensions per skill
SKILL_RUBRICS: dict[str, dict] = {
    "author": {
        "dimensions": {
            "fsm_architecture":    {"weight": 25, "labels": ["fsm:*"]},
            "action_quality":      {"weight": 20, "labels": ["actions:*"]},
            "safety_compliance":   {"weight": 20, "labels": ["safety:*"]},
            "instruction_quality": {"weight": 15, "labels": ["instructions:*"]},
            "process_quality":     {"weight": 10, "labels": ["process:*"]},
            "conversational":      {"weight": 10, "labels": ["chat:*"]},
        }
    },
    "discover": {
        "dimensions": {
            "target_identification": {"weight": 40, "labels": ["discover:target-found"]},
            "fuzzy_matching":        {"weight": 30, "labels": ["discover:fuzzy-match"]},
            "completeness":          {"weight": 30, "labels": ["discover:missing-identified"]},
        }
    },
    "scaffold": {
        "dimensions": {
            "compilation":    {"weight": 40, "labels": ["scaffold:compiles"]},
            "field_mapping":  {"weight": 35, "labels": ["scaffold:field-mapping"]},
            "test_coverage":  {"weight": 25, "labels": ["scaffold:test-coverage"]},
        }
    },
    "deploy": {
        "dimensions": {
            "clean_deploy":    {"weight": 30, "labels": ["deploy:clean-deploy"]},
            "component_count": {"weight": 20, "labels": ["deploy:component-count"]},
            "publish":         {"weight": 25, "labels": ["deploy:publish-success"]},
            "activate":        {"weight": 25, "labels": ["deploy:activate-success"]},
        }
    },
    "test": {
        "dimensions": {
            "smoke_pass":            {"weight": 40, "labels": ["test:smoke-pass"]},
            "utterance_coverage":    {"weight": 30, "labels": ["test:utterance-coverage"]},
            "conversation_quality":  {"weight": 30, "labels": ["test:conversation-quality"]},
        }
    },
    "optimize": {
        "dimensions": {
            "issue_identification": {"weight": 30, "labels": ["optimize:issue-identified"]},
            "fix_quality":          {"weight": 30, "labels": ["optimize:fix-applied"]},
            "regression_safety":    {"weight": 20, "labels": ["optimize:regression-free"]},
            "stdm_analysis":        {"weight": 20, "labels": ["optimize:stdm-analyzed"]},
        }
    },
    # outcome — business outcome measurement from scenario execution
    "outcome": {
        "dimensions": {
            "task_completion":          {"weight": 30, "labels": ["outcome:task-completion", "outcome:first-contact-resolution"]},
            "action_accuracy":          {"weight": 30, "labels": ["outcome:correct-action", "outcome:correct-params"]},
            "conversation_efficiency":  {"weight": 20, "labels": ["outcome:minimal-turns", "outcome:helpful-response"]},
            "escalation_quality":       {"weight": 20, "labels": ["outcome:appropriate-escalation"]},
        }
    },
    # grounding — response grounding from preview trace analysis
    # Note: grounding_rate accounts for expected SMALL_TALK on safety/scope/edge categories.
    # SMALL_TALK is acceptable (not a failure) when the utterance is a safety probe,
    # scope/guardrail test, or edge case where clarifying questions are valid.
    "grounding": {
        "dimensions": {
            "grounding_rate":   {"weight": 40, "labels": ["grounding:grounded"]},
            "accuracy":         {"weight": 30, "labels": ["grounding:no-hallucination"]},
            "first_attempt":    {"weight": 15, "labels": ["grounding:no-retry"]},
            "safety":           {"weight": 15, "labels": ["grounding:safety-score"]},
        }
    },
    # conversation — multi-turn quality from transcript analysis
    "conversation": {
        "dimensions": {
            "naturalness":  {"weight": 25, "labels": ["conversation:no-repetition", "conversation:graceful-recovery"]},
            "helpfulness":  {"weight": 35, "labels": ["conversation:proactive-guidance", "outcome:helpful-response"]},
            "resilience":   {"weight": 20, "labels": ["conversation:context-retained", "conversation:graceful-recovery"]},
            "tone":         {"weight": 20, "labels": ["conversation:tone-appropriate"]},
        }
    },
}


def _label_matches(label: str, patterns: list[str]) -> bool:
    """Check if a label matches any of the given glob patterns."""
    return any(fnmatch.fnmatch(label, p) for p in patterns)


def compute_skill_score(
    skill: str,
    verdicts: list[dict],
) -> Optional[dict]:
    """Compute per-dimension scores for a skill based on assertion verdicts.

    Args:
        skill: Skill name (e.g., "author", "deploy")
        verdicts: List of verdict dicts with "label" and "result" keys

    Returns:
        {"dimensions": {dim_name: score_0_to_5}, "overall": float_0_to_100}
        or None if the skill has no rubric or no matching verdicts.
    """
    rubric = SKILL_RUBRICS.get(skill)
    if not rubric:
        return None

    dimensions = {}
    total_weight = 0
    weighted_sum = 0.0

    for dim_name, dim_cfg in rubric["dimensions"].items():
        patterns = dim_cfg["labels"]
        matching = [v for v in verdicts if _label_matches(v.get("label", ""), patterns)]

        if not matching:
            dimensions[dim_name] = None
            continue

        passed = sum(1 for v in matching if v.get("result") == "PASS")
        total = len(matching)
        ratio = passed / total if total else 0
        score = round(ratio * 5, 2)  # 0-5 scale

        dimensions[dim_name] = score
        total_weight += dim_cfg["weight"]
        weighted_sum += (ratio * dim_cfg["weight"])

    if total_weight == 0:
        return None

    overall = round(weighted_sum / total_weight * 100, 1)

    return {"dimensions": dimensions, "overall": overall}


def grade_letter(score: float) -> str:
    """Convert a 0-100 score to a letter grade."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def grade_color(score: float) -> str:
    """Return a CSS color for a 0-100 score."""
    if score >= 90:
        return "#16a34a"
    if score >= 75:
        return "#2563eb"
    if score >= 60:
        return "#ca8a04"
    if score >= 40:
        return "#ea580c"
    return "#dc2626"
