#!/usr/bin/env python3
"""Generate interactive HTML report from ADLC eval summary.json."""

import argparse
import json
import sys
from pathlib import Path


def load_json(path):
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def escape_html(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def truncate(s, n=200):
    if not s:
        return ""
    s = str(s)
    return s[:n] + "..." if len(s) > n else s


def grade_color(score):
    if score >= 90: return "#16a34a"
    if score >= 75: return "#2563eb"
    if score >= 60: return "#ca8a04"
    if score >= 40: return "#ea580c"
    return "#dc2626"


def grade_letter(score):
    if score >= 90: return "A"
    if score >= 75: return "B"
    if score >= 60: return "C"
    if score >= 40: return "D"
    return "F"


def bar_color(pct):
    if pct >= 80: return "#16a34a"
    if pct >= 60: return "#2563eb"
    if pct >= 40: return "#ca8a04"
    return "#ea580c"


PIPELINE_STEPS_ORDER = ["author", "discover", "scaffold", "deploy", "test", "optimize"]
# Additional rubric dimensions that aren't pipeline steps but appear in skill_scores
EXTRA_RUBRIC_SKILLS = ["outcome", "grounding", "conversation"]

# Map pipeline steps to consolidated skill names
PIPELINE_SKILL_MAP = {
    "author": "agentforce-development",
    "discover": "agentforce-development",
    "scaffold": "agentforce-development",
    "deploy": "agentforce-development",
    "test": "agentforce-testing",
    "optimize": "agentforce-observability",
}

# Per-skill insight templates keyed by dimension name
SKILL_INSIGHTS = {
    "author": {
        "title": "Agent Authoring",
        "dimensions": {
            "fsm_architecture": {
                "name": "FSM Architecture",
                "description": "Quality of finite state machine design: topics, transitions, hub-and-spoke patterns",
                "good": "Clean hub-and-spoke routing with specialized topics and proper transitions",
                "bad": "Missing transitions, flat topic structure, no router pattern",
                "recommendation": "Use router-only start_agent with explicit transition actions per topic"
            },
            "action_quality": {
                "name": "Action Quality",
                "description": "Action definitions, I/O types, slot-filling, available-when guards",
                "good": "Well-defined actions with proper inputs/outputs, slot-filling for conversation, guards for gating",
                "bad": "Missing I/O types, no slot-filling, ungated sensitive actions",
                "recommendation": "Use slot-filling (...) for multi-field collection; add available-when guards for sensitive actions"
            },
            "safety_compliance": {
                "name": "Safety Compliance",
                "description": "AI disclosure, scope boundaries, data handling, content safety",
                "good": "Clear AI disclosure, defined scope boundaries, no unsafe patterns",
                "bad": "Missing AI disclosure, unbounded scope, potential data leakage",
                "recommendation": "Always include AI disclosure in system instructions and explicit scope limitations"
            },
            "instruction_quality": {
                "name": "Instruction Quality",
                "description": "Clarity and effectiveness of system and topic instructions",
                "good": "Action-oriented literal instructions with explicit tool names",
                "bad": "Passive/vague instructions that cause LLM deflection",
                "recommendation": "Use literal instructions (|) with explicit step-by-step tool naming for complex workflows"
            },
            "process_quality": {
                "name": "Process Quality",
                "description": "Skill invocation, routing, multi-turn interaction handling",
                "good": "Correct skill routing, proper artifact handoff between steps",
                "bad": "Wrong skill invoked, artifacts lost between steps",
                "recommendation": "Ensure each pipeline step produces well-structured artifacts for downstream consumption"
            },
            "conversational": {
                "name": "Conversational Flow",
                "description": "Natural conversation handling, error recovery, multi-turn coherence",
                "good": "Smooth topic transitions, natural slot-filling, graceful error handling",
                "bad": "Abrupt transitions, rigid input requirements, poor error messages",
                "recommendation": "Design for natural conversation flow with graceful fallbacks"
            },
        }
    },
    "discover": {
        "title": "Target Discovery",
        "dimensions": {
            "target_identification": {
                "name": "Target Identification",
                "description": "Accuracy of identifying existing targets in the org",
                "good": "All targets correctly identified as present or missing",
                "bad": "False positives or missed targets",
                "recommendation": "Verify target names match exactly (case-sensitive, namespace-aware)"
            },
            "fuzzy_matching": {
                "name": "Fuzzy Matching",
                "description": "Ability to match similar target names across naming conventions",
                "good": "Detects renamed or similarly-named targets",
                "bad": "Misses obvious matches due to naming differences",
                "recommendation": "Consider namespace prefixes and naming convention differences"
            },
            "completeness": {
                "name": "Completeness",
                "description": "All action targets from .agent file are accounted for",
                "good": "Every target in the .agent file has a found/missing status",
                "bad": "Some targets silently skipped or not checked",
                "recommendation": "Parse all action definitions including nested and conditional ones"
            },
        }
    },
    "scaffold": {
        "title": "Stub Scaffolding",
        "dimensions": {
            "compilation": {
                "name": "Compilation",
                "description": "Generated code compiles and deploys without errors",
                "good": "All generated classes, flows, and tests compile cleanly",
                "bad": "Syntax errors, invalid class names, missing imports",
                "recommendation": "Validate class naming conventions (no dots in Apex names)"
            },
            "field_mapping": {
                "name": "Field Mapping",
                "description": "I/O fields correctly mapped between .agent and generated code",
                "good": "All input/output fields match .agent action definitions",
                "bad": "Missing fields, wrong types, mismatched names",
                "recommendation": "Map complex_data_type_name correctly per target type (flow vs apex)"
            },
            "test_coverage": {
                "name": "Test Coverage",
                "description": "Generated test classes cover all Apex targets",
                "good": "Every Apex class has a corresponding test class with assertions",
                "bad": "Missing test classes or empty test methods",
                "recommendation": "Generate test classes that exercise all @InvocableMethod entry points"
            },
        }
    },
    "deploy": {
        "title": "Deployment",
        "dimensions": {
            "clean_deploy": {
                "name": "Clean Deploy",
                "description": "All components deployed without errors",
                "good": "Zero deployment errors, all components pushed successfully",
                "bad": "Component failures, partial deploys, permission errors",
                "recommendation": "Validate metadata XML before deploying; check API version compatibility"
            },
            "component_count": {
                "name": "Component Count",
                "description": "Expected number of components deployed",
                "good": "All scaffolded components plus agent bundle deployed",
                "bad": "Missing components, unexpected count",
                "recommendation": "Track component manifest from scaffold to deploy"
            },
            "publish": {
                "name": "Publish Success",
                "description": "Agent bundle published to the org",
                "good": "Bundle published with correct bot version",
                "bad": "Publish failed (common: Internal Error for new agents)",
                "recommendation": "If publish fails for new agents, create shell in Setup UI first"
            },
            "activate": {
                "name": "Activation",
                "description": "Agent activated and ready for preview",
                "good": "Agent activated and available for testing",
                "bad": "Activation failed or agent stuck in inactive state",
                "recommendation": "Ensure publish completes before activation"
            },
        }
    },
    "test": {
        "title": "Agent Testing",
        "dimensions": {
            "smoke_pass": {
                "name": "Smoke Test Pass Rate",
                "description": "Percentage of test utterances that pass",
                "good": "All utterances routed correctly with correct grounding (GROUNDED or expected SMALL_TALK)",
                "bad": "Utterances fail with unexpected SMALL_TALK grounding or wrong routing",
                "recommendation": "Fix grounding issues by ensuring actions produce factual content"
            },
            "utterance_coverage": {
                "name": "Utterance Coverage",
                "description": "Test utterances cover all agent topics",
                "good": "At least one utterance per topic with diverse intents",
                "bad": "Topics untested or only happy-path covered",
                "recommendation": "Add edge cases: ambiguous intents, multi-topic, off-topic"
            },
            "conversation_quality": {
                "name": "Conversation Quality",
                "description": "Response quality, naturalness, and accuracy",
                "good": "Responses are accurate, contextual, and well-formatted",
                "bad": "Generic errors, incomplete responses, hallucinations",
                "recommendation": "Review response content for factual accuracy and completeness"
            },
        }
    },
    "optimize": {
        "title": "Agent Optimization",
        "dimensions": {
            "issue_identification": {
                "name": "Issue Detection",
                "description": "Ability to identify problems from session traces",
                "good": "Root cause identified with trace evidence and clear diagnosis",
                "bad": "Symptoms described but root cause missed",
                "recommendation": "Analyze trace chains: routing → action calls → grounding → response"
            },
            "fix_quality": {
                "name": "Fix Effectiveness",
                "description": "Quality and correctness of applied fixes",
                "good": "Fix resolves the issue and is verified with passing tests",
                "bad": "Fix applied but issue persists or introduces regressions",
                "recommendation": "Verify fixes with targeted re-testing before declaring success"
            },
            "regression_safety": {
                "name": "Regression Safety",
                "description": "Other topics still work after optimization changes",
                "good": "Cross-topic regression test passes all topics",
                "bad": "Fix breaks other topics or introduces new failures",
                "recommendation": "Always run full regression after any .agent file change"
            },
            "stdm_analysis": {
                "name": "STDM Analysis",
                "description": "Use of STDM traces from Data Cloud for analysis",
                "good": "STDM DMOs queried, quality scores analyzed, moments reviewed",
                "bad": "Fell back to local traces without attempting STDM",
                "recommendation": "Query STDM DMOs when available for richer session analysis"
            },
        }
    },
    "outcome": {
        "title": "Business Outcomes",
        "dimensions": {
            "task_completion": {
                "name": "Task Completion",
                "description": "Agent completes the user's intended task end-to-end",
                "good": "All scenarios resolved successfully with correct outcomes",
                "bad": "Scenarios left incomplete or resolved incorrectly",
                "recommendation": "Check action chains: are all required actions invoked in the right order?"
            },
            "action_accuracy": {
                "name": "Action Accuracy",
                "description": "Correct action selected with correct parameters",
                "good": "Right action called with correct user-provided values",
                "bad": "Wrong action selected or parameters missing/incorrect",
                "recommendation": "Improve action descriptions to distinguish between similar actions"
            },
            "conversation_efficiency": {
                "name": "Conversation Efficiency",
                "description": "Task completed in a reasonable number of turns",
                "good": "Resolved within expected turn count without unnecessary back-and-forth",
                "bad": "Too many turns to complete a simple task",
                "recommendation": "Use slot-filling (...) to collect multiple inputs in one turn"
            },
            "escalation_quality": {
                "name": "Escalation Quality",
                "description": "Escalated at the right time — not too early, not too late",
                "good": "Escalated when appropriate, attempted resolution first",
                "bad": "Escalated too eagerly or failed to escalate when needed",
                "recommendation": "Add turn count thresholds and explicit escalation triggers"
            },
        }
    },
    "grounding": {
        "title": "Response Grounding",
        "dimensions": {
            "grounding_rate": {
                "name": "Grounding Rate",
                "description": "Percentage of responses with correct grounding (GROUNDED, or expected SMALL_TALK for safety/scope/edge categories)",
                "good": "All responses correctly grounded — SMALL_TALK only on safety probes, scope deflections, and edge cases",
                "bad": "Unexpected SMALL_TALK on routing/action utterances (agent guessing instead of invoking actions)",
                "recommendation": "Ensure actions produce factual data; use {!@variables} in instructions for grounding"
            },
            "accuracy": {
                "name": "Factual Accuracy",
                "description": "Response content matches actual action output data",
                "good": "Response references real data from actions, no hallucination",
                "bad": "Response contains information not returned by any action",
                "recommendation": "Use is_displayable on outputs and reference variables in instructions"
            },
            "first_attempt": {
                "name": "First Attempt Success",
                "description": "Response grounded on first attempt without retry",
                "good": "Single ReasoningStep per turn — no UNGROUNDED retry cycles",
                "bad": "Multiple ReasoningSteps indicate UNGROUNDED retry",
                "recommendation": "Avoid intermediate actions that produce no user-facing content"
            },
            "safety": {
                "name": "Platform Safety",
                "description": "Platform safety score meets threshold",
                "good": "Safety score >= 0.9 on all responses",
                "bad": "Safety score below threshold",
                "recommendation": "Review system instructions for safety guideline compliance"
            },
        }
    },
    "conversation": {
        "title": "Conversation Quality",
        "dimensions": {
            "naturalness": {
                "name": "Naturalness",
                "description": "Conversation flows naturally without robotic repetition",
                "good": "Varied responses, no repeated questions or redundant info",
                "bad": "Agent repeats the same question or gives template responses",
                "recommendation": "Use procedural instructions (->) with variable-based branching"
            },
            "helpfulness": {
                "name": "Helpfulness",
                "description": "Responses advance the user toward their goal",
                "good": "Each response moves the conversation forward with relevant info or actions",
                "bad": "Responses are vague, off-topic, or don't address the user's need",
                "recommendation": "Ensure instructions explicitly guide toward task completion"
            },
            "resilience": {
                "name": "Context Resilience",
                "description": "Maintains context across turns and topic switches",
                "good": "Variables persist, context carries across transitions",
                "bad": "Agent forgets earlier context or asks for info already provided",
                "recommendation": "Use agent-level mutable variables that persist across topic transitions"
            },
            "tone": {
                "name": "Tone Appropriateness",
                "description": "Response tone matches the business domain",
                "good": "Tone is professional, empathetic, and domain-appropriate",
                "bad": "Tone is too casual for finance, too formal for retail, or inconsistent",
                "recommendation": "Set explicit tone guidelines in system instructions"
            },
        }
    },
}


def load_test_data(run_dir, test_id):
    """Load all artifact data from the test results directory."""
    test_dir = Path(run_dir) / test_id
    data = {}

    # Load .agent file — try nested structure (recursive) first, then flat fallback
    author_dir = test_dir / "author" / "artifacts"
    if author_dir.exists():
        for f in author_dir.rglob("*.agent"):
            data["agent_file_content"] = f.read_text()
            data["agent_file_name"] = f.name
            break
    if "agent_file_content" not in data:
        # Flat structure fallback (older runs: <test-id>/Agent.agent)
        for f in test_dir.glob("*.agent"):
            data["agent_file_content"] = f.read_text()
            data["agent_file_name"] = f.name
            break

    # Load invocation JSONs for each skill
    for skill in PIPELINE_STEPS_ORDER:
        inv_path = test_dir / skill / "invocation.json"
        inv = load_json(inv_path)
        if inv:
            data[f"{skill}_invocation"] = inv

    # Load conversations
    conv_path = test_dir / "test" / "conversations.json"
    conv = load_json(conv_path)
    if conv:
        data["conversations"] = conv

    # Load scenarios
    scenarios_path = test_dir / "test" / "scenarios.json"
    scenarios = load_json(scenarios_path)
    if scenarios:
        data["scenarios"] = scenarios

    # Load verdicts
    verdicts_path = test_dir / "verdicts.json"
    verdicts = load_json(verdicts_path)
    if verdicts:
        data["verdicts"] = verdicts

    # Load spec — try run-local first, then evals/specs/ directory
    spec_path = test_dir / "spec.md"
    if spec_path.exists():
        data["spec_content"] = spec_path.read_text()
    else:
        # Try evals/specs/ directory (run_dir is evals/results/run-xxx, so evals/ is 2 up)
        evals_dir = Path(run_dir).parent.parent
        for candidate in evals_dir.glob("specs/*.md"):
            # Match by test_id substring (e.g., "target-store" matches "target-store-assistant.md")
            test_slug = test_id.replace("-full-cycle", "").replace("-e2e", "")
            if test_slug in candidate.stem:
                data["spec_content"] = candidate.read_text()
                break

    # Load judge analysis files (produced by eval-author-judge and eval-test-judge skills)
    author_analysis_path = test_dir / "author" / "analysis.json"
    author_analysis = load_json(author_analysis_path)
    if author_analysis:
        data["author_analysis"] = author_analysis
        # Auto-merge design review insights into top-level fields if not already present
        design_review = author_analysis.get("design_review", {})
        if design_review.get("strengths"):
            data.setdefault("author_strengths", design_review["strengths"])
        if design_review.get("weaknesses"):
            data.setdefault("author_weaknesses", design_review["weaknesses"])
        if design_review.get("risks"):
            data.setdefault("author_risks", design_review["risks"])

    test_analysis_path = test_dir / "test" / "analysis.json"
    test_analysis = load_json(test_analysis_path)
    if test_analysis:
        data["test_analysis"] = test_analysis

    # Load scaffold file list from artifacts dir
    scaffold_dir = test_dir / "scaffold" / "artifacts"
    if scaffold_dir.exists():
        scaffold_files = []
        for f in sorted(scaffold_dir.rglob("*")):
            if f.is_file():
                scaffold_files.append(str(f.relative_to(scaffold_dir)))
        data["scaffold_files"] = scaffold_files

    # Load deploy file list
    deploy_dir = test_dir / "deploy" / "force-app"
    if deploy_dir.exists():
        deploy_files = []
        for f in sorted(deploy_dir.rglob("*")):
            if f.is_file() and "genAiPlannerBundles" not in str(f) and ".sfdx" not in str(f):
                deploy_files.append(str(f.relative_to(deploy_dir.parent)))
        data["deploy_files"] = deploy_files

    return data


CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card-bg: #f9fafb; --accent: #2563eb; --success: #16a34a;
  --warning: #ca8a04; --danger: #dc2626;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--fg); line-height: 1.6; padding: 24px; max-width: 1200px; margin: 0 auto; font-size: 14px; }
h1 { font-size: 26px; font-weight: 700; margin-bottom: 4px; }
h2 { font-size: 18px; font-weight: 600; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid var(--border); }
h3 { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.subtitle { color: var(--muted); font-size: 13px; margin-bottom: 20px; }

.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
.summary-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
.summary-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.summary-card .value { font-size: 24px; font-weight: 700; margin-top: 2px; }

.grade-badge { display: inline-block; padding: 3px 12px; border-radius: 16px; font-weight: 700; font-size: 13px; color: #fff; }
.tag { display: inline-block; padding: 1px 6px; border-radius: 3px; background: #eff6ff; color: var(--accent); font-size: 10px; margin-right: 3px; }
.tag-success { background: #f0fdf4; color: #16a34a; }
.tag-fail { background: #fef2f2; color: #dc2626; }
.tag-warn { background: #fefce8; color: #ca8a04; }
.tag-neutral { background: #f3f4f6; color: #6b7280; }

.dim-scores { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; margin-bottom: 12px; }
.dim-score { padding: 8px 12px; border-radius: 6px; background: #fff; border: 1px solid var(--border); font-size: 12px; }
.dim-score .dim-name { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; }
.dim-score .dim-val { font-weight: 600; font-size: 14px; }
.bar { height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; margin-top: 3px; }
.bar-fill { height: 100%; border-radius: 3px; }

.test-case { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.test-case-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.test-case-id { font-size: 11px; color: var(--muted); font-family: monospace; }

.pipeline-viz { display: flex; align-items: center; gap: 0; margin: 12px 0; flex-wrap: wrap; }
.pipeline-step { display: flex; align-items: center; gap: 0; }
.pipeline-dot { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: #fff; }
.pipeline-dot.success { background: #16a34a; }
.pipeline-dot.fail { background: #dc2626; }
.pipeline-dot.skip { background: #d1d5db; color: #6b7280; }
.pipeline-dot.partial { background: #ca8a04; }
.pipeline-arrow { width: 24px; height: 2px; background: var(--border); }
.pipeline-label { font-size: 9px; color: var(--muted); text-align: center; margin-top: 2px; }
.pipeline-step-wrapper { display: flex; flex-direction: column; align-items: center; }

.heatmap-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.heatmap-table th { text-align: left; padding: 6px 10px; background: var(--card-bg); border-bottom: 2px solid var(--border); font-size: 11px; color: var(--muted); }
.heatmap-table td { padding: 4px 10px; border-bottom: 1px solid #f3f4f6; }
.heatmap-bar { height: 8px; border-radius: 4px; background: var(--border); overflow: hidden; min-width: 60px; }
.heatmap-fill { height: 100%; border-radius: 4px; }

.verdicts-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.verdicts-table th { text-align: left; padding: 6px 8px; background: var(--card-bg); border-bottom: 2px solid var(--border); font-size: 10px; color: var(--muted); }
.verdicts-table td { padding: 4px 8px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
.verdict-pass { color: #16a34a; font-weight: 600; }
.verdict-fail { color: #dc2626; font-weight: 600; }

.tab-container { margin-top: 12px; }
.tab-buttons { display: flex; gap: 0; border-bottom: 2px solid var(--border); flex-wrap: wrap; }
.tab-btn { padding: 6px 14px; font-size: 12px; border: none; background: none; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -2px; white-space: nowrap; }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tab-panel { display: none; padding: 12px 0; }
.tab-panel.active { display: block; }

.agent-code { white-space: pre-wrap; word-break: break-word; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; background: #1e1e2e; color: #cdd6f4; padding: 16px; border-radius: 8px; border: 1px solid #313244; max-height: 600px; overflow-y: auto; line-height: 1.5; }
.agent-code .line-num { color: #585b70; user-select: none; display: inline-block; width: 3em; text-align: right; margin-right: 1em; }
.log-content { white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 11px; background: #fefce8; padding: 12px; border-radius: 6px; border: 1px solid #fef08a; max-height: 400px; overflow-y: auto; }
.json-content { white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 11px; background: #f0f9ff; padding: 12px; border-radius: 6px; border: 1px solid #bae6fd; max-height: 500px; overflow-y: auto; }

.msg-container { max-height: 700px; overflow-y: auto; padding: 8px; }
.msg-row { padding: 10px 14px; margin-bottom: 6px; border-radius: 8px; font-size: 13px; border-left: 3px solid transparent; }
.msg-row.msg-pass { background: #f0fdf4; border-left-color: #22c55e; }
.msg-row.msg-fail { background: #fef2f2; border-left-color: #ef4444; }
.msg-row.msg-user { background: #f0f9ff; border-left-color: #3b82f6; }
.msg-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.msg-icon { font-size: 14px; }
.msg-role { font-weight: 600; font-size: 11px; text-transform: uppercase; }
.msg-meta { font-size: 10px; color: var(--muted); margin-left: auto; }
.msg-body { line-height: 1.5; }
.msg-text { white-space: pre-wrap; word-break: break-word; }

.comparison { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.comparison h3 { color: #166534; margin-bottom: 8px; }
.comparison table { width: 100%; border-collapse: collapse; }
.comparison th, .comparison td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #bbf7d0; font-size: 12px; }
.comparison th { color: var(--muted); font-weight: 500; }
.improvement { color: #16a34a; font-weight: 600; }
.regression { color: #dc2626; font-weight: 600; }
.neutral { color: var(--muted); }

.stats-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
.stats-table td { padding: 4px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
.stats-table td:first-child { color: var(--muted); width: 180px; }

.skill-card { background: #fff; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.skill-card-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.skill-card-header:hover { background: #f9fafb; }
.skill-card-body { padding: 0 16px 16px; }
.skill-dim-row { display: grid; grid-template-columns: 180px 60px 1fr; gap: 8px; align-items: start; padding: 10px 0; border-bottom: 1px solid #f3f4f6; font-size: 12px; }
.skill-dim-row:last-child { border-bottom: none; }
.skill-dim-name { font-weight: 600; }
.skill-dim-desc { color: var(--muted); font-size: 11px; margin-top: 2px; }
.skill-dim-score { font-weight: 700; font-size: 14px; text-align: center; }
.insight-box { background: #f8fafc; border-radius: 6px; padding: 8px 12px; font-size: 11px; line-height: 1.5; }
.insight-label { font-weight: 600; color: var(--muted); font-size: 10px; text-transform: uppercase; margin-bottom: 2px; }
.insight-good { border-left: 3px solid #16a34a; }
.insight-bad { border-left: 3px solid #dc2626; }
.insight-rec { border-left: 3px solid #2563eb; }
.insight-finding { border-left: 3px solid #ca8a04; background: #fffbeb; }

.file-tree { font-family: monospace; font-size: 11px; line-height: 1.8; max-height: 400px; overflow-y: auto; }
.file-tree .file-icon { color: var(--muted); margin-right: 4px; }
.file-cls { color: #2563eb; }
.file-xml { color: #ca8a04; }
.file-test { color: #16a34a; }
.file-flow { color: #7c3aed; }
.file-perm { color: #ea580c; }

details { cursor: pointer; }
details summary { font-size: 11px; color: var(--muted); padding: 2px 0; }
details[open] summary { margin-bottom: 8px; }

.footer { margin-top: 36px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); text-align: center; }

/* Mobile-responsive table wrapper */
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 0 -4px; padding: 0 4px; }

/* Ensure all tables and code blocks respect container width */
table { table-layout: auto; }
.verdicts-table td, .stats-table td, .heatmap-table td { word-break: break-word; }

@media (max-width: 768px) {
  html { overflow-x: hidden; }
  body { padding: 10px; font-size: 13px; max-width: 100vw; overflow-x: hidden; width: 100%; }
  h1 { font-size: 20px; }
  h2 { font-size: 16px; margin: 20px 0 10px; }
  .summary-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .summary-card .value { font-size: 18px; }
  .dim-scores { grid-template-columns: 1fr; }
  .skill-dim-row { grid-template-columns: 1fr; gap: 4px; }
  .skill-dim-score { text-align: left; }
  .pipeline-viz { gap: 0; justify-content: center; }
  .pipeline-arrow { width: 12px; }
  .pipeline-dot { width: 24px; height: 24px; font-size: 9px; }
  .pipeline-label { font-size: 8px; }
  .tab-container { overflow: hidden; width: 100%; }
  .tab-buttons { overflow-x: auto; -webkit-overflow-scrolling: touch; flex-wrap: nowrap; scrollbar-width: none; -ms-overflow-style: none; }
  .tab-buttons::-webkit-scrollbar { display: none; }
  .tab-btn { padding: 6px 10px; font-size: 11px; flex-shrink: 0; }
  .tab-panel { overflow-x: hidden; overflow-y: visible; width: 100%; max-width: 100vw; }
  .tab-panel .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .heatmap-table, .verdicts-table, .stats-table { font-size: 11px; width: 100%; table-layout: fixed; }
  .verdicts-table td, .verdicts-table th { padding: 4px 4px; word-break: break-word; overflow-wrap: break-word; }
  .heatmap-table td, .heatmap-table th { padding: 4px 6px; }
  /* Hide less-critical columns on mobile */
  .verdicts-table th:nth-child(2), .verdicts-table td:nth-child(2),
  .verdicts-table th:nth-child(4), .verdicts-table td:nth-child(4),
  .verdicts-table th:nth-child(6), .verdicts-table td:nth-child(6) { display: none; }
  .test-case { padding: 12px; overflow: hidden; width: 100%; box-sizing: border-box; }
  .test-case-header { flex-direction: column; gap: 8px; }
  .msg-container { max-height: none; overflow-y: visible; }
  .msg-row { padding: 8px 10px; }
  .agent-code { font-size: 10px; padding: 10px; max-height: none; overflow-y: visible; word-break: break-all; }
  .agent-code .line-num { width: 2.5em; margin-right: 0.5em; }
  .skill-card-header { padding: 10px 12px; }
  .skill-card-body { padding: 0 12px 12px; }
  .insight-box { font-size: 10px; padding: 6px 8px; }
  .stats-table { table-layout: fixed; width: 100%; }
  .stats-table td:first-child { width: 40%; min-width: 80px; }
  .stats-table td { word-break: break-word; overflow-wrap: break-word; }
  .comparison { overflow: hidden; }
  .comparison table { table-layout: fixed; width: 100%; }
  .comparison th, .comparison td { padding: 4px 6px; font-size: 11px; word-break: break-word; }
  .json-content, .log-content { font-size: 10px; padding: 8px; max-height: none; overflow-y: visible; word-break: break-all; }
  .msg-body, .msg-text { font-size: 12px; }
}

@media (max-width: 480px) {
  body { padding: 6px; width: 100%; }
  .summary-grid { grid-template-columns: 1fr 1fr; gap: 6px; }
  .summary-card { padding: 8px 10px; }
  .summary-card .value { font-size: 16px; }
  .summary-card .label { font-size: 10px; }
  .tag { font-size: 9px; padding: 1px 4px; }
  .verdicts-table, .heatmap-table, .stats-table { font-size: 10px; }
  .verdicts-table td, .verdicts-table th { padding: 3px 3px; }
  .tab-btn { padding: 5px 8px; font-size: 10px; }
  .pipeline-dot { width: 20px; height: 20px; font-size: 8px; }
  .pipeline-arrow { width: 8px; }
  .test-case { padding: 8px; overflow: hidden; }
  .msg-row { padding: 6px 8px; font-size: 12px; }
  .agent-code { max-height: none; }
  .json-content, .log-content { max-height: none; }
}
"""

JS = """
function showTab(caseId, tabName) {
  var panel = document.getElementById(caseId + '-' + tabName);
  if (!panel) return;
  var container = panel.closest('.tab-container');
  container.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
  container.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
  panel.classList.add('active');
  event.target.classList.add('active');
}
function toggleSkill(id) {
  var el = document.getElementById(id);
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
"""


def render_pipeline_viz(test):
    """Render horizontal pipeline step visualization."""
    pipeline = test.get("pipeline", ["author"])
    pipeline_results = test.get("pipeline_results", {})
    html = '<div class="pipeline-viz">\n'
    for i, step in enumerate(PIPELINE_STEPS_ORDER):
        if i > 0:
            html += '  <div class="pipeline-arrow"></div>\n'
        if step in pipeline:
            result = pipeline_results.get(step, {})
            status = result.get("status", "skip")
            status_map = {"success": "success", "completed": "success", "partial": "partial", "fail": "fail", "error": "fail", "skipped": "skip"}
            css_class = status_map.get(status, "skip")
            icon = {"success": "&#10003;", "partial": "~", "fail": "&#10007;", "skip": "-"}
            dot_icon = icon.get(css_class, "-")
        else:
            css_class = "skip"
            dot_icon = "-"
        skill_name = PIPELINE_SKILL_MAP.get(step, "")
        html += f'  <div class="pipeline-step-wrapper" title="{skill_name}">\n'
        html += f'    <div class="pipeline-dot {css_class}">{dot_icon}</div>\n'
        html += f'    <div class="pipeline-label">{step}</div>\n'
        html += f'  </div>\n'
    html += '</div>\n'
    return html


def render_verdict_row(v):
    """Render a single assertion verdict table row."""
    result = v.get("result", "?")
    css = "verdict-pass" if result == "PASS" else "verdict-fail"
    conf = v.get("confidence", "")
    conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else str(conf)
    evidence = escape_html(truncate(v.get("evidence", ""), 150))
    reason = escape_html(truncate(v.get("reason", ""), 200))
    # Add insight and recommendation for richer verdicts
    insight = v.get("insight", "")
    recommendation = v.get("recommendation", "")
    extra = ""
    if insight:
        extra += f'<div style="margin-top:3px; font-size:10px; color:var(--muted)"><em>{escape_html(truncate(insight, 150))}</em></div>'
    if recommendation and result != "PASS":
        extra += f'<div style="margin-top:2px; font-size:10px; color:var(--accent)">Fix: {escape_html(truncate(recommendation, 150))}</div>'
    return f"""<tr>
  <td><code>{escape_html(v.get('label', ''))}</code></td>
  <td>{escape_html(v.get('type', 'positive'))}</td>
  <td class="{css}">{result}</td>
  <td>{conf_str}</td>
  <td>{reason}{extra}</td>
  <td><small>{evidence}</small></td>
</tr>"""


def _render_utterance_pair(u):
    """Render a single user→agent utterance pair."""
    utt = u.get("utterance", "")
    resp = u.get("response", "")
    result = u.get("result", "?")
    expected = u.get("expected_topic", "")
    actual = u.get("actual_topics", [])
    grounding = u.get("grounding", "")
    failure = u.get("failure_reason", "")

    result_tag = f'<span class="tag tag-success">PASS</span>' if result == "PASS" else f'<span class="tag tag-fail">FAIL</span>'
    grounding_tag = ""
    if grounding:
        grounding_pass = u.get("grounding_pass")
        category = u.get("category", "")
        if grounding == "GROUNDED":
            gcls = "tag-success"
        elif grounding == "SMALL_TALK" and (grounding_pass or category in ("safety", "scope", "guardrail", "edge")):
            gcls = "tag-neutral"
        else:
            gcls = "tag-fail"
        grounding_tag = f' <span class="tag {gcls}">{escape_html(grounding)}</span>'
    topic_str = " > ".join(actual) if actual else "?"

    html = f'''<div class="msg-row msg-user">
  <div class="msg-header">
    <span class="msg-icon">&#128100;</span>
    <span class="msg-role">User</span>
    <span class="msg-meta">expected: {escape_html(expected)}</span>
  </div>
  <div class="msg-body"><div class="msg-text">{escape_html(utt)}</div></div>
</div>\n'''

    res_class = "msg-pass" if result == "PASS" else "msg-fail"
    actions = u.get("actions_invoked", [])
    actions_str = ", ".join(actions) if actions else ""
    html += f'''<div class="msg-row {res_class}">
  <div class="msg-header">
    <span class="msg-icon">&#129302;</span>
    <span class="msg-role">Agent</span>
    <span class="msg-meta">{result_tag}{grounding_tag} route: {escape_html(topic_str)}</span>
  </div>
  <div class="msg-body"><div class="msg-text">{escape_html(resp)}</div></div>'''
    if actions_str:
        html += f'\n  <div style="margin-top:4px; font-size:10px; color:var(--muted)">Actions: <code>{escape_html(actions_str)}</code></div>'
    if failure:
        html += f'\n  <div style="margin-top:4px; padding:6px 10px; background:#fef2f2; border-radius:4px; font-size:11px; color:#dc2626">{escape_html(failure)}</div>'
    # Render judge-enriched insight, recommendation, root_cause
    insight = u.get("insight", "")
    recommendation = u.get("recommendation", "")
    root_cause = u.get("root_cause", {})
    resp_quality = u.get("response_quality", "")
    if insight:
        html += f'\n  <div style="margin-top:4px; padding:6px 10px; background:#f0f9ff; border-radius:4px; font-size:11px; color:#1e40af"><strong>Insight:</strong> {escape_html(truncate(insight, 250))}</div>'
    if root_cause and isinstance(root_cause, dict):
        rc_text = root_cause.get("description", root_cause.get("category", ""))
        if rc_text:
            html += f'\n  <div style="margin-top:2px; padding:6px 10px; background:#fffbeb; border-radius:4px; font-size:11px; color:#92400e"><strong>Root cause:</strong> {escape_html(truncate(str(rc_text), 200))}</div>'
    if recommendation and result != "PASS":
        html += f'\n  <div style="margin-top:2px; padding:6px 10px; background:#f0fdf4; border-radius:4px; font-size:11px; color:#166534"><strong>Fix:</strong> {escape_html(truncate(recommendation, 200))}</div>'
    if resp_quality and result != "PASS":
        html += f'\n  <div style="margin-top:2px; font-size:10px; color:var(--muted)">Quality: {escape_html(truncate(str(resp_quality), 100))}</div>'
    html += '\n</div>\n'
    return html


def render_conversation(conv_data):
    """Render test conversation data grouped by session/category."""
    if not conv_data:
        return '<p style="color:var(--muted)">No preview conversations captured.</p>'

    utterances = conv_data.get("utterances", conv_data) if isinstance(conv_data, dict) else conv_data
    if not isinstance(utterances, list):
        return '<p style="color:var(--muted)">No preview conversations captured.</p>'

    # Group utterances by session_id
    from collections import OrderedDict
    sessions = OrderedDict()
    for u in utterances:
        if not isinstance(u, dict):
            continue
        sid = u.get("session_id", "unknown")
        sessions.setdefault(sid, []).append(u)

    # Determine if sessions are single-turn (smoke tests) or multi-turn
    single_turn_sessions = []
    multi_turn_sessions = []
    for sid, turns in sessions.items():
        if len(turns) == 1:
            single_turn_sessions.append((sid, turns))
        else:
            multi_turn_sessions.append((sid, turns))

    # Category labels and icons
    cat_labels = {
        "routing": "Routing",
        "action": "Action Invocation",
        "edge": "Edge Cases",
        "safety": "Safety Probes",
        "scope": "Scope Boundaries",
        "multi-intent": "Multi-Intent",
        "guardrail": "Guardrails",
    }
    cat_icons = {
        "routing": "&#128268;",   # link
        "action": "&#9889;",      # zap
        "edge": "&#128736;",      # wrench
        "safety": "&#128737;",    # shield
        "scope": "&#128683;",     # no entry
        "multi-intent": "&#128256;", # twisted arrows
        "guardrail": "&#128683;",
    }

    html = '<div class="msg-container">\n'

    # Render single-turn sessions grouped by category
    if single_turn_sessions:
        # Group by category
        by_cat = OrderedDict()
        for sid, turns in single_turn_sessions:
            cat = turns[0].get("category", "other")
            by_cat.setdefault(cat, []).extend(turns)

        for cat, utts in by_cat.items():
            label = cat_labels.get(cat, cat.replace("_", " ").title())
            icon = cat_icons.get(cat, "&#128172;")
            pass_count = sum(1 for u in utts if u.get("result") == "PASS")
            total = len(utts)
            rate_pct = (pass_count / total * 100) if total else 0
            rate_cls = "tag-success" if pass_count == total else "tag-fail" if pass_count == 0 else "tag-warn"

            html += f'''<details class="session-group" open>
<summary style="cursor:pointer; padding:8px 12px; background:var(--card-bg); border:1px solid var(--border); border-radius:6px; margin-bottom:6px; font-size:12px; font-weight:600; display:flex; align-items:center; gap:8px">
  <span>{icon} {escape_html(label)}</span>
  <span class="tag {rate_cls}" style="margin-left:auto">{pass_count}/{total}</span>
</summary>
<div style="padding:0 0 8px 0">\n'''
            for u in utts:
                html += f'<div style="margin:0 0 2px 12px; border-left:3px solid var(--border); padding-left:10px">\n'
                html += _render_utterance_pair(u)
                html += '</div>\n'
            html += '</div>\n</details>\n'

    # Render multi-turn sessions as conversation threads
    if multi_turn_sessions:
        html += '<h4 style="margin:16px 0 8px; font-size:13px">Multi-Turn Conversations</h4>\n'
        for i, (sid, turns) in enumerate(multi_turn_sessions, 1):
            pass_count = sum(1 for u in turns if u.get("result") == "PASS")
            total = len(turns)
            rate_cls = "tag-success" if pass_count == total else "tag-fail" if pass_count == 0 else "tag-warn"
            short_sid = sid[:8] if sid and sid != "unknown" else f"session-{i}"

            html += f'''<details class="session-group" open>
<summary style="cursor:pointer; padding:8px 12px; background:var(--card-bg); border:1px solid var(--border); border-radius:6px; margin-bottom:6px; font-size:12px; font-weight:600; display:flex; align-items:center; gap:8px">
  <span>&#128172; Conversation #{i} <span style="font-weight:400; color:var(--muted)">({short_sid})</span></span>
  <span style="font-weight:400; color:var(--muted)">{total} turns</span>
  <span class="tag {rate_cls}" style="margin-left:auto">{pass_count}/{total}</span>
</summary>
<div style="padding:0 0 8px 12px; border-left:3px solid var(--border); margin-left:12px">\n'''
            for u in turns:
                html += _render_utterance_pair(u)
            html += '</div>\n</details>\n'

    # Summary with detailed metrics
    if isinstance(conv_data, dict) and "summary" in conv_data:
        s = conv_data["summary"]
        rate = s.get("pass_rate", 0)
        html += f'<div style="margin-top:12px; padding:12px 14px; background:#f0f9ff; border-radius:6px; font-size:12px; line-height:1.8">'
        html += f'<strong>Results:</strong> {s.get("passed", 0)}/{s.get("total", 0)} passed ({rate:.0%})'
        if s.get("partial"):
            html += f' &middot; {s["partial"]} partial'
        if s.get("failed"):
            html += f' &middot; {s["failed"]} failed'
        if s.get("skipped"):
            html += f' &middot; {s["skipped"]} skipped'
        html += '<br>'
        if s.get("routing_total"):
            r_rate = s.get("routing_rate", 0)
            r_color = grade_color(r_rate * 100) if isinstance(r_rate, (int, float)) else "var(--fg)"
            html += f'<strong>Routing:</strong> <span style="color:{r_color}">{s.get("routing_correct", 0)}/{s["routing_total"]} correct ({r_rate:.0%})</span> &middot; '
        if s.get("total"):
            g_rate = s.get("grounding_rate", 0)
            g_color = grade_color(g_rate * 100) if isinstance(g_rate, (int, float)) else "var(--fg)"
            grounded_n = s.get("grounded_count", 0)
            expected_st = s.get("expected_small_talk_count", 0)
            unexpected_st = s.get("unexpected_small_talk_count", 0)
            g_pass = s.get("grounding_pass_count", grounded_n + expected_st)
            g_detail = f"{grounded_n} GROUNDED"
            if expected_st:
                g_detail += f", {expected_st} expected SMALL_TALK"
            if unexpected_st:
                g_detail += f", {unexpected_st} unexpected SMALL_TALK"
            html += f'<strong>Grounding:</strong> <span style="color:{g_color}">{g_pass}/{s["total"]} correct ({g_rate:.0%})</span> <span style="font-size:11px;color:var(--muted)">({g_detail})</span>'
        html += '</div>\n'

    html += '</div>\n'
    return html


def render_scenarios(scenario_data):
    """Render scenario execution results as grouped conversations."""
    if not scenario_data:
        return ''

    scenarios = scenario_data.get("scenarios", scenario_data) if isinstance(scenario_data, dict) else scenario_data
    if not isinstance(scenarios, list):
        return ''

    html = '<h4 style="margin: 16px 0 8px; font-size: 13px">Scenarios</h4>\n'
    for sc in scenarios:
        if not isinstance(sc, dict):
            continue
        name = sc.get("name", "Unnamed scenario")
        status = sc.get("actual_outcome", sc.get("status", "unknown"))
        status_cls = "tag-success" if status in ("completed", "task-completed") else "tag-fail"
        total_turns = sc.get("total_turns", len(sc.get("turns", [])))
        max_turns = sc.get("max_turns", "?")

        html += f'<details style="margin-bottom:8px; border:1px solid var(--border); border-radius:6px; padding:8px">\n'
        html += f'<summary style="cursor:pointer; font-size:12px; font-weight:600">'
        html += f'{escape_html(name)} <span class="tag {status_cls}">{escape_html(status)}</span>'
        html += f' <span style="color:var(--muted); font-weight:400">({total_turns}/{max_turns} turns)</span></summary>\n'
        html += '<div class="msg-container" style="margin-top:8px">\n'

        for turn in sc.get("turns", []):
            if not isinstance(turn, dict):
                continue
            user_msg = turn.get("user", "")
            resp = turn.get("response", "")
            result = turn.get("result", "?")
            expected_topic = turn.get("expected_topic", "")
            actual_topic = turn.get("actual_topic", "")
            expected_action = turn.get("expected_action", "")
            actual_action = turn.get("actual_action", "")
            grounding = turn.get("grounding", "")

            result_tag = f'<span class="tag tag-success">PASS</span>' if result == "PASS" else f'<span class="tag tag-fail">FAIL</span>'
            grounding_tag = ""
            if grounding:
                grounding_pass = turn.get("grounding_pass")
                turn_category = turn.get("category", "")
                if grounding == "GROUNDED":
                    gcls = "tag-success"
                elif grounding == "SMALL_TALK" and (grounding_pass or turn_category in ("safety", "scope", "guardrail", "edge")):
                    gcls = "tag-neutral"
                else:
                    gcls = "tag-fail"
                grounding_tag = f' <span class="tag {gcls}">{escape_html(grounding)}</span>'

            meta_parts = []
            if expected_topic:
                match = "✓" if actual_topic == expected_topic else "✗"
                meta_parts.append(f"topic: {actual_topic or '?'} {match}")
            if expected_action:
                match = "✓" if actual_action == expected_action else "✗"
                meta_parts.append(f"action: {actual_action or '?'} {match}")
            meta_str = " | ".join(meta_parts)

            # User turn
            html += f'''<div class="msg-row msg-user">
  <div class="msg-header">
    <span class="msg-icon">&#128100;</span>
    <span class="msg-role">User</span>
    <span class="msg-meta">expect: {escape_html(expected_topic)} {escape_html(expected_action)}</span>
  </div>
  <div class="msg-body"><div class="msg-text">{escape_html(user_msg)}</div></div>
</div>\n'''

            # Agent response
            if resp:
                res_class = "msg-pass" if result == "PASS" else "msg-fail"
                html += f'''<div class="msg-row {res_class}">
  <div class="msg-header">
    <span class="msg-icon">&#129302;</span>
    <span class="msg-role">Agent</span>
    <span class="msg-meta">{result_tag}{grounding_tag} {escape_html(meta_str)}</span>
  </div>
  <div class="msg-body"><div class="msg-text">{escape_html(resp)}</div></div>
</div>\n'''

        html += '</div>\n</details>\n'

    # Scenario summary
    if isinstance(scenario_data, dict) and "summary" in scenario_data:
        s = scenario_data["summary"]
        html += f'<div style="margin-top:8px; padding:10px; background:#f0f9ff; border-radius:6px; font-size:12px">'
        html += f'<strong>Scenarios:</strong> {s.get("scenarios_completed", 0)}/{s.get("scenarios_total", 0)} completed'
        if s.get("avg_turns"):
            html += f' | avg {s["avg_turns"]:.1f} turns'
        if s.get("containment_rate") is not None:
            html += f' | {s["containment_rate"]:.0%} containment'
        html += '</div>\n'

    return html


def render_agent_file(content):
    """Render .agent file with syntax highlighting."""
    if not content:
        return '<p style="color:var(--muted)">No .agent file captured.</p>'

    lines = content.split('\n')
    html = '<pre class="agent-code">'
    for i, line in enumerate(lines, 1):
        num = f'<span class="line-num">{i}</span>'
        html += f'{num}{escape_html(line)}\n'
    html += '</pre>'
    return html


def file_icon_class(fname):
    """Return CSS class for file type."""
    if fname.endswith("Test.cls"):
        return "file-test"
    if fname.endswith(".cls"):
        return "file-cls"
    if fname.endswith(".xml"):
        return "file-xml"
    if "flow" in fname.lower():
        return "file-flow"
    if "permissionset" in fname.lower():
        return "file-perm"
    return ""


def render_file_tree(files, title="Files"):
    """Render a file list as a tree."""
    if not files:
        return f'<p style="color:var(--muted)">No {title.lower()} captured.</p>'
    html = f'<p style="font-size:12px; margin-bottom:8px"><strong>{len(files)} {title}</strong></p>\n'
    html += '<div class="file-tree">\n'
    for f in files:
        cls = file_icon_class(f)
        icon = "&#128196;" if f.endswith(".cls") else "&#128221;" if f.endswith(".xml") else "&#128206;"
        html += f'  <div><span class="file-icon">{icon}</span><span class="{cls}">{escape_html(f)}</span></div>\n'
    html += '</div>\n'
    return html


def render_invocation_json(inv_data, skill_name):
    """Render invocation.json data as a formatted card."""
    if not inv_data:
        return f'<p style="color:var(--muted)">No {skill_name} data captured.</p>'
    return f'<pre class="json-content">{escape_html(json.dumps(inv_data, indent=2))}</pre>'


def render_skill_insights(skill_name, skill_score, verdicts, invocation_data):
    """Render per-skill insight card with dimensions, reasons, and recommendations."""
    insight_def = SKILL_INSIGHTS.get(skill_name)
    if not insight_def:
        return ""

    overall = skill_score.get("overall", 0) if skill_score else 0
    dimensions = skill_score.get("dimensions", {}) if skill_score else {}

    # Don't render card if no dimensions have actual scores — avoids misleading "0% F"
    if not dimensions or not any(v is not None for v in dimensions.values()):
        return ""

    skill_id = f"skill-{skill_name}"

    html = f'<div class="skill-card">\n'
    html += f'<div class="skill-card-header" onclick="toggleSkill(\'{skill_id}-body\')">\n'
    parent_skill = PIPELINE_SKILL_MAP.get(skill_name, "")
    parent_tag = f' &middot; <code style="font-size:10px">{escape_html(parent_skill)}</code>' if parent_skill else ""
    html += f'  <div><h3 style="margin:0">{escape_html(insight_def["title"])}</h3>'
    html += f'  <span style="font-size:11px; color:var(--muted)">{skill_name}{parent_tag}</span></div>\n'
    html += f'  <div style="text-align:right">'
    html += f'    <span style="font-size:20px; font-weight:700">{overall:.0f}%</span> '
    html += f'    <span class="grade-badge" style="background:{grade_color(overall)}">{grade_letter(overall)}</span>'
    html += f'  </div>\n'
    html += f'</div>\n'
    html += f'<div class="skill-card-body" id="{skill_id}-body">\n'

    for dim_key, dim_info in insight_def["dimensions"].items():
        score = dimensions.get(dim_key)
        score_display = f"{score}/5" if score is not None else "N/A"
        score_pct = (score / 5 * 100) if score is not None else 0
        score_color = bar_color(score_pct) if score is not None else "#d1d5db"

        # Determine pass/fail for this dimension from verdicts
        passed = score is not None and score >= 4.0

        html += f'<div class="skill-dim-row">\n'
        html += f'  <div>\n'
        html += f'    <div class="skill-dim-name">{escape_html(dim_info["name"])}</div>\n'
        html += f'    <div class="skill-dim-desc">{escape_html(dim_info["description"])}</div>\n'
        html += f'  </div>\n'
        html += f'  <div class="skill-dim-score" style="color:{score_color}">{score_display}</div>\n'
        html += f'  <div>\n'

        if passed:
            html += f'    <div class="insight-box insight-good"><div class="insight-label">What worked</div>{escape_html(dim_info["good"])}</div>\n'
        elif score is not None:
            html += f'    <div class="insight-box insight-bad"><div class="insight-label">Issue</div>{escape_html(dim_info["bad"])}</div>\n'
            html += f'    <div class="insight-box insight-rec" style="margin-top:4px"><div class="insight-label">Recommendation</div>{escape_html(dim_info["recommendation"])}</div>\n'
        else:
            html += f'    <div class="insight-box"><div class="insight-label">Not evaluated</div>No matching assertions for this dimension</div>\n'

        html += f'  </div>\n'
        html += f'</div>\n'

    # Key finding from invocation data
    if invocation_data:
        key_finding = invocation_data.get("key_finding", "")
        if key_finding:
            html += f'<div class="insight-box insight-finding" style="margin-top:8px"><div class="insight-label">Key Finding</div>{escape_html(key_finding)}</div>\n'
        issues = invocation_data.get("issues_encountered", invocation_data.get("issues_identified", []))
        if isinstance(issues, list) and issues:
            for issue in issues:
                if isinstance(issue, dict):
                    desc = issue.get("description", "")
                    sev = issue.get("severity", issue.get("priority", ""))
                    tag_cls = "tag-fail" if sev in ("P1", "ERROR") else "tag-warn"
                    html += f'<div class="insight-box insight-finding" style="margin-top:4px">'
                    html += f'<div class="insight-label">Issue <span class="tag {tag_cls}">{escape_html(sev)}</span></div>'
                    html += f'{escape_html(desc)}</div>\n'

    html += '</div>\n</div>\n'
    return html


def render_optimize_details(inv_data):
    """Render optimization details: fix attempts, verification, etc."""
    if not inv_data:
        return '<p style="color:var(--muted)">No optimization data captured.</p>'

    html = ''

    # Summary stats (always show if available — works with flat pipeline_results format)
    status = inv_data.get("status", "")
    if status:
        status_cls = "success" if status in ("success", "completed") else "warn" if status == "partial" else "fail"
        html += '<div class="table-wrap"><table class="stats-table">\n'
        html += f'  <tr><td>Status</td><td><span class="tag tag-{status_cls}">{escape_html(status)}</span></td></tr>\n'
        if inv_data.get("stdm_available") is not None:
            html += f'  <tr><td>STDM Available</td><td>{"Yes" if inv_data["stdm_available"] else "No (local traces only)"}</td></tr>\n'
        if inv_data.get("stdm_records") is not None:
            html += f'  <tr><td>STDM Records</td><td>{inv_data["stdm_records"]}</td></tr>\n'
        sessions = inv_data.get("sessions_analyzed")
        if sessions is not None:
            html += f'  <tr><td>Sessions Analyzed</td><td>{sessions}</td></tr>\n'
        traces = inv_data.get("traces_analyzed") or inv_data.get("local_traces_analyzed")
        if traces is not None:
            html += f'  <tr><td>Traces Analyzed</td><td>{traces}</td></tr>\n'
        if inv_data.get("historical_moments_analyzed") is not None:
            html += f'  <tr><td>Historical Moments</td><td>{inv_data["historical_moments_analyzed"]}</td></tr>\n'
        findings_count = inv_data.get("findings_count")
        if findings_count is not None:
            html += f'  <tr><td>Findings</td><td>{findings_count}</td></tr>\n'
        if inv_data.get("note"):
            html += f'  <tr><td>Note</td><td>{escape_html(inv_data["note"])}</td></tr>\n'
        # Show issues_found as count if it's a number, skip if it's a list (rendered below)
        issues_found_val = inv_data.get("issues_found")
        if isinstance(issues_found_val, (int, float)):
            html += f'  <tr><td>Issues Found</td><td>{issues_found_val}</td></tr>\n'
        rec_val = inv_data.get("recommendations")
        if isinstance(rec_val, (int, float)):
            html += f'  <tr><td>Recommendations</td><td>{rec_val}</td></tr>\n'
        elif isinstance(rec_val, list) and rec_val:
            html += f'  <tr><td>Recommendations</td><td>{len(rec_val)}</td></tr>\n'
        if inv_data.get("start_time"):
            html += f'  <tr><td>Duration</td><td>{escape_html(inv_data.get("start_time", ""))} &rarr; {escape_html(inv_data.get("end_time", ""))}</td></tr>\n'
        html += '</table></div>\n'

    # Issues identified — check multiple key names
    issues = inv_data.get("issues_identified", []) or inv_data.get("issues_found", []) or inv_data.get("findings", [])
    if issues and isinstance(issues, list):
        html += '<h4 style="margin:8px 0 6px; font-size:13px">Issues Identified</h4>\n'
        severity_colors = {"high": "tag-fail", "critical": "tag-fail", "medium": "tag-warn", "low": "tag-info"}
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            sev = issue.get("severity", issue.get("priority", ""))
            sev_cls = severity_colors.get(sev.lower(), "tag-warn") if sev else "tag-warn"
            category = issue.get("category", "Issue")
            desc = issue.get("description", "")
            affected = issue.get("affected_topic", issue.get("affected_component", ""))
            recommendation = issue.get("recommendation", "")
            html += f'<div class="insight-box insight-finding" style="margin-bottom:8px; padding:10px">'
            html += f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:4px">'
            html += f'<span class="tag {sev_cls}" style="text-transform:uppercase">{escape_html(sev)}</span>'
            html += f'<strong>{escape_html(category)}</strong>'
            if affected:
                html += f' <span style="color:var(--muted); font-size:11px">({escape_html(affected)})</span>'
            html += '</div>'
            html += f'<div style="margin-bottom:4px">{escape_html(desc)}</div>'
            if recommendation:
                html += f'<div style="font-size:11px; color:var(--muted)"><strong>Recommendation:</strong> {escape_html(recommendation)}</div>'
            trace = issue.get("trace_evidence", {})
            if trace:
                html += f'<div style="margin-top:6px; font-size:10px; color:var(--muted)">'
                for k, v in trace.items():
                    html += f'<div><strong>{escape_html(k)}:</strong> {escape_html(str(v))}</div>'
                html += '</div>'
            html += '</div>\n'

    # Fix attempts
    attempts = inv_data.get("fix_attempts", [])
    if attempts:
        html += '<h4 style="margin:12px 0 6px; font-size:13px">Fix Attempts</h4>\n'
        html += '<div class="table-wrap"><table class="verdicts-table"><thead><tr><th>#</th><th>Description</th><th>Result</th></tr></thead><tbody>\n'
        for att in attempts:
            if not isinstance(att, dict):
                continue
            num = att.get("attempt", "?")
            desc = att.get("description", "")
            result = att.get("result", "")
            is_pass = "PASS" in result.upper()
            css = "verdict-pass" if is_pass else "verdict-fail"
            html += f'<tr><td>{num}</td><td>{escape_html(desc)}</td><td class="{css}">{escape_html(result)}</td></tr>\n'
        html += '</tbody></table></div>\n'

    # Verification
    verify = inv_data.get("verification", {})
    if verify:
        html += '<h4 style="margin:12px 0 6px; font-size:13px">Verification</h4>\n'
        html += '<pre class="json-content">' + escape_html(json.dumps(verify, indent=2)) + '</pre>\n'

    # Recommendations list
    recs = inv_data.get("recommendations", [])
    if recs and isinstance(recs, list):
        html += '<h4 style="margin:12px 0 6px; font-size:13px">Recommendations</h4>\n'
        if isinstance(recs[0], dict):
            # Structured recs with priority/action/effort/impact
            html += '<div class="table-wrap"><table class="stats-table"><thead><tr><th>Priority</th><th>Action</th><th>Effort</th><th>Impact</th></tr></thead><tbody>\n'
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                pri = rec.get("priority", "")
                pri_cls = "tag-fail" if pri == "P0" else "tag-warn" if pri == "P1" else "tag-info"
                html += f'<tr><td><span class="tag {pri_cls}">{escape_html(pri)}</span></td>'
                html += f'<td>{escape_html(rec.get("action", ""))}</td>'
                html += f'<td>{escape_html(rec.get("effort", ""))}</td>'
                html += f'<td>{escape_html(rec.get("impact", ""))}</td></tr>\n'
            html += '</tbody></table></div>\n'
        else:
            # Simple string list
            html += '<ul style="margin:4px 0; padding-left:20px">\n'
            for rec in recs:
                html += f'<li>{escape_html(str(rec))}</li>\n'
            html += '</ul>\n'

    # STDM moments
    stdm = inv_data.get("stdm_moments", [])
    if stdm and isinstance(stdm, list):
        html += '<h4 style="margin:12px 0 6px; font-size:13px">STDM Production Moments</h4>\n'
        html += '<div class="table-wrap"><table class="stats-table"><thead><tr><th>Request</th><th>Response</th></tr></thead><tbody>\n'
        for m in stdm:
            if not isinstance(m, dict):
                continue
            html += f'<tr><td>{escape_html(m.get("request", ""))}</td><td>{escape_html(m.get("response", ""))}</td></tr>\n'
        html += '</tbody></table></div>\n'

    # Key finding
    key_finding = inv_data.get("key_finding", "")
    if key_finding:
        html += f'<div class="insight-box insight-finding" style="margin-top:8px"><div class="insight-label">Key Finding</div>{escape_html(key_finding)}</div>\n'

    return html


def generate_report(summary, output_path, compare=None, summary_path=None):
    """Generate self-contained HTML report from summary.json data."""

    suite_name = summary.get("suite_name", "ADLC Eval")
    timestamp = summary.get("timestamp", "")
    overall_pct = round(summary.get("overall_score", 0) * 100, 1)
    tests = summary.get("tests", [])
    by_label = summary.get("by_label", {})
    by_tag = summary.get("by_tag", {})
    skills_discovered = summary.get("skills_discovered", [])
    skill_dim_avgs = summary.get("skill_dimension_averages", {})

    # Determine run directory for loading artifacts
    # summary_path may be at run-level (results/run-xxx/summary.json) or
    # test-level (results/run-xxx/<test-id>/summary.json). load_test_data
    # expects the run dir (parent of test dirs).
    if summary_path:
        sp = Path(summary_path).parent
        # If summary is inside a test subdir (test_id matches dir name), go up one level
        test_ids = {t.get("test_id", "") for t in tests}
        if sp.name in test_ids:
            run_dir = sp.parent
        else:
            run_dir = sp
    else:
        run_dir = None

    # Header + Summary grid
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ADLC Eval Report &mdash; {escape_html(suite_name)}</title>
<style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
<h1>ADLC Eval Report</h1>
<p class="subtitle">{escape_html(suite_name)} &mdash; {escape_html(timestamp)}</p>

<div class="summary-grid">
  <div class="summary-card">
    <div class="label">Overall Score</div>
    <div class="value">{overall_pct}%</div>
  </div>
  <div class="summary-card">
    <div class="label">Grade</div>
    <div class="value"><span class="grade-badge" style="background:{grade_color(overall_pct)}">{grade_letter(overall_pct)}</span></div>
  </div>
  <div class="summary-card">
    <div class="label">Test Cases</div>
    <div class="value">{summary.get('total_tests', len(tests))}</div>
  </div>
  <div class="summary-card">
    <div class="label">Assertions</div>
    <div class="value">{summary.get('passed_assertions', 0)}/{summary.get('total_assertions', 0)}</div>
  </div>
  <div class="summary-card">
    <div class="label">Pipeline Steps</div>
    <div class="value">{sum(len(t.get('pipeline', ['author'])) for t in tests)}</div>
  </div>
  {'<div class="summary-card"><div class="label">Skills Discovered</div><div class="value">' + str(len(skills_discovered)) + '</div></div>' if skills_discovered else ''}
</div>
"""

    # Executive Summary (from eval-report skill or auto-generated from data)
    exec_summary = summary.get("executive_summary", "")
    if not exec_summary and tests:
        # Auto-generate from available data
        t0 = tests[0]
        test_name = t0.get("test_id", "Unknown")
        pipeline = t0.get("pipeline", ["author"])
        convs = t0.get("conversations", {})
        conv_summary = convs.get("summary", {}) if isinstance(convs, dict) else {}
        fails = [v for v in t0.get("assertions_results", []) if isinstance(v, dict) and v.get("result") == "FAIL"]
        partials = [v for v in t0.get("assertions_results", []) if isinstance(v, dict) and v.get("result") == "PARTIAL"]
        routing_rate = conv_summary.get("routing_rate", 0)
        grounding_rate = conv_summary.get("grounding_rate", 0)
        parts = [f"<strong>{escape_html(test_name)}</strong> &mdash; {len(pipeline)}-step pipeline"]
        parts.append(f"scored <strong>{overall_pct}% ({grade_letter(overall_pct)})</strong>")
        if conv_summary.get("total"):
            parts.append(f"{conv_summary.get('passed', 0)}/{conv_summary['total']} utterances passed")
        if fails:
            parts.append(f"<strong>{len(fails)} assertion{'s' if len(fails) != 1 else ''} failed</strong>: " +
                         ", ".join(escape_html(f.get("label", "?")) for f in fails[:3]))
        exec_summary = ". ".join(parts) + "."

    if exec_summary:
        html += f'<div class="insight-box" style="margin-bottom:20px; font-size:13px; line-height:1.7; padding:16px; border-left:4px solid var(--accent)">\n'
        html += f'  <div class="insight-label" style="font-size:11px; margin-bottom:6px">Executive Summary</div>\n'
        html += f'  {exec_summary}\n'
        html += f'</div>\n'

    # Key Findings (from eval-report skill or auto-extracted from verdicts)
    key_findings = summary.get("key_findings", [])
    if not key_findings and tests:
        # Auto-extract: FAIL verdicts with reasons as findings
        for t in tests:
            for v in t.get("assertions_results", []):
                if not isinstance(v, dict):
                    continue
                if v.get("result") in ("FAIL", "PARTIAL"):
                    severity = "critical" if "FAIL" == v.get("result") else "medium"
                    key_findings.append({
                        "title": v.get("label", "Unknown"),
                        "severity": severity,
                        "explanation": v.get("reason", ""),
                        "recommendation": v.get("recommendation", v.get("insight", "")),
                    })
        # Also add conversation failures
        for t in tests:
            convs = t.get("conversations", {})
            if isinstance(convs, dict):
                for u in convs.get("utterances", []):
                    if not isinstance(u, dict):
                        continue
                    if u.get("result") in ("FAIL", "SKIP"):
                        key_findings.append({
                            "title": f"Utterance: {truncate(u.get('utterance', ''), 60)}",
                            "severity": "high" if u.get("result") == "FAIL" else "medium",
                            "explanation": u.get("failure_reason", f"Result: {u.get('result')} | Grounding: {u.get('grounding', 'N/A')}"),
                            "recommendation": "",
                        })

    if key_findings:
        html += '<h2>Key Findings</h2>\n'
        severity_colors = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04", "low": "#6b7280"}
        severity_bg = {"critical": "#fef2f2", "high": "#fff7ed", "medium": "#fefce8", "low": "#f9fafb"}
        for i, f in enumerate(key_findings[:8], 1):
            sev = f.get("severity", "medium")
            color = severity_colors.get(sev, "#6b7280")
            bg = severity_bg.get(sev, "#f9fafb")
            html += f'<div style="background:{bg}; border-left:3px solid {color}; border-radius:6px; padding:10px 14px; margin-bottom:8px; font-size:12px">\n'
            html += f'  <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px">'
            html += f'<span style="background:{color}; color:#fff; padding:1px 8px; border-radius:3px; font-size:10px; font-weight:600; text-transform:uppercase">{escape_html(sev)}</span>'
            html += f'<strong>{escape_html(f.get("title", ""))}</strong></div>\n'
            if f.get("explanation"):
                html += f'  <div style="color:#374151; line-height:1.5">{escape_html(f["explanation"])}</div>\n'
            if f.get("recommendation"):
                html += f'  <div style="margin-top:4px; color:var(--accent); font-size:11px"><strong>Fix:</strong> {escape_html(f["recommendation"])}</div>\n'
            html += f'</div>\n'

    # Spec Compliance Matrix (from eval-author-judge or summary)
    spec_compliance = summary.get("spec_compliance", [])
    if not spec_compliance and tests:
        for t in tests:
            sc = t.get("spec_compliance", [])
            if sc:
                spec_compliance = sc
                break
    if spec_compliance:
        html += '<h2>Spec Compliance Matrix</h2>\n'
        html += '<div class="table-wrap"><table class="verdicts-table">\n'
        html += '<thead><tr><th>Requirement</th><th>Status</th><th>Notes</th></tr></thead>\n<tbody>\n'
        for item in spec_compliance:
            if not isinstance(item, dict):
                continue
            status = item.get("status", "").upper()
            status_cls = "verdict-pass" if status in ("MATCH", "PASS") else "verdict-fail"
            html += f'<tr><td>{escape_html(item.get("requirement", ""))}</td>'
            html += f'<td class="{status_cls}">{escape_html(status)}</td>'
            html += f'<td>{escape_html(item.get("notes", ""))}</td></tr>\n'
        html += '</tbody></table></div>\n'

    # Recommended Actions (from eval-report skill)
    actions = summary.get("recommended_actions", [])
    if actions:
        html += '<h2>Recommended Actions</h2>\n'
        for i, act in enumerate(actions, 1):
            if isinstance(act, dict):
                priority = act.get("priority", f"P{i}")
                html += f'<div class="insight-box insight-rec" style="margin-bottom:6px"><strong>{escape_html(priority)}:</strong> {escape_html(act.get("action", ""))}'
                if act.get("effort"):
                    html += f' <span style="color:var(--muted); font-size:10px">({escape_html(act["effort"])})</span>'
                html += '</div>\n'
            elif isinstance(act, str):
                html += f'<div class="insight-box insight-rec" style="margin-bottom:6px"><strong>P{i}:</strong> {escape_html(act)}</div>\n'

    # Business Metrics (from summary)
    biz = summary.get("business_metrics", {})
    if biz:
        html += '<h2>Business Metrics</h2>\n'
        html += '<div class="summary-grid" style="grid-template-columns: repeat(auto-fit, minmax(140px, 1fr))">\n'
        metric_labels = {
            "containment_rate": ("Containment", True), "routing_accuracy": ("Routing Accuracy", True),
            "grounding_rate": ("Grounding Rate", True), "safety_pass_rate": ("Safety", True),
            "error_rate": ("Error Rate", False), "scope_adherence": ("Scope Adherence", True),
            "avg_turns_to_resolution": ("Avg Turns", False), "avg_response_time_ms": ("Avg Response", False),
        }
        for key, (label, is_pct) in metric_labels.items():
            val = biz.get(key)
            if val is None:
                continue
            if is_pct:
                display = f"{val * 100:.0f}%" if isinstance(val, float) and val <= 1 else f"{val}%"
                score_pct = val * 100 if isinstance(val, float) and val <= 1 else val
                color = grade_color(score_pct) if key != "error_rate" else grade_color(100 - score_pct)
            elif key == "avg_response_time_ms":
                display = f"{val:,.0f}ms" if isinstance(val, (int, float)) else str(val)
                color = grade_color(100 if val < 3000 else 60 if val < 5000 else 30)
            else:
                display = str(val)
                color = "var(--fg)"
            html += f'  <div class="summary-card"><div class="label">{escape_html(label)}</div><div class="value" style="font-size:18px; color:{color}">{display}</div></div>\n'
        html += '</div>\n'

    # Comparison section
    if compare:
        prev_pct = round(compare.get("overall_score", 0) * 100, 1)
        delta = round(overall_pct - prev_pct, 1)
        delta_class = "improvement" if delta > 0 else "regression" if delta < 0 else "neutral"
        delta_sign = "+" if delta > 0 else ""
        html += f"""<div class="comparison">
  <h3>Run Comparison</h3>
  <div class="table-wrap"><table>
    <tr><th>Metric</th><th>Previous</th><th>Current</th><th>Change</th></tr>
    <tr><td>Overall Score</td><td>{prev_pct}%</td><td>{overall_pct}%</td><td class="{delta_class}">{delta_sign}{delta}pts</td></tr>
    <tr><td>Grade</td><td>{grade_letter(prev_pct)}</td><td>{grade_letter(overall_pct)}</td><td class="{delta_class}">{'Improved' if delta > 0 else 'Same' if delta == 0 else 'Regressed'}</td></tr>
    <tr><td>Tests</td><td>{compare.get('total_tests', '?')}</td><td>{summary.get('total_tests', '?')}</td><td class="neutral">-</td></tr>
    <tr><td>Passed Assertions</td><td>{compare.get('passed_assertions', '?')}/{compare.get('total_assertions', '?')}</td><td>{summary.get('passed_assertions', '?')}/{summary.get('total_assertions', '?')}</td><td class="neutral">-</td></tr>
  </table></div>
</div>
"""

    # By-label heatmap
    if by_label:
        html += '<h2>Assertion Results by Label</h2>\n'
        html += '<div class="table-wrap"><table class="heatmap-table">\n'
        html += '<thead><tr><th>Label</th><th>Passed</th><th>Failed</th><th>Total</th><th>Rate</th><th></th></tr></thead>\n'
        html += '<tbody>\n'
        for label, stats in sorted(by_label.items()):
            passed = stats.get("passed", 0)
            total = stats.get("total", 0)
            failed = total - passed
            pct = (passed / total * 100) if total else 0
            html += f"""<tr>
  <td><code>{escape_html(label)}</code></td>
  <td>{passed}</td><td>{failed}</td><td>{total}</td>
  <td>{pct:.0f}%</td>
  <td><div class="heatmap-bar"><div class="heatmap-fill" style="width:{pct:.0f}%; background:{bar_color(pct)};"></div></div></td>
</tr>\n"""
        html += '</tbody></table></div>\n'

    # Skill Dimension Averages
    if skill_dim_avgs:
        html += '<h2>Skill Dimension Averages</h2>\n'
        html += '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px; margin-bottom:24px">\n'
        for skill, dims in sorted(skill_dim_avgs.items()):
            parent_skill = PIPELINE_SKILL_MAP.get(skill, "")
            parent_label = f' <span style="font-size:10px; color:var(--muted)">({parent_skill})</span>' if parent_skill else ""
            html += f'<div class="summary-card"><h3 style="margin-bottom:8px; font-size:13px; text-transform:capitalize">{escape_html(skill)}{parent_label}</h3>\n'
            for dim_name, dim_val in sorted(dims.items()):
                if dim_val is None:
                    continue
                dim_pct = (dim_val / 5 * 100) if isinstance(dim_val, (int, float)) else 0
                dim_label = dim_name.replace("_", " ").title()
                html += f'<div style="margin-bottom:6px"><div style="display:flex; justify-content:space-between; font-size:11px"><span style="color:var(--muted)">{escape_html(dim_label)}</span><span style="font-weight:600">{dim_val}/5</span></div>'
                html += f'<div class="bar"><div class="bar-fill" style="width:{dim_pct:.0f}%; background:{bar_color(dim_pct)}"></div></div></div>\n'
            html += '</div>\n'
        html += '</div>\n'

    # Per-test-case cards
    html += '<h2>Test Case Results</h2>\n'

    for test in tests:
        test_id = test.get("test_id", "unknown")
        tab_id = test_id.replace("-", "").replace("_", "")
        score_pct = round(test.get("score", 0) * 100, 1)
        status = test.get("status", "")
        if not status:
            # Derive from pipeline_results — all success = PASS, any failure = FAIL
            pr = test.get("pipeline_results", {})
            if pr:
                statuses = [v.get("status", "") for v in pr.values() if isinstance(v, dict)]
                if all(s == "success" for s in statuses):
                    status = "PASS"
                elif any(s in ("error", "failure") for s in statuses):
                    status = "FAIL"
                else:
                    status = "PARTIAL"
            else:
                status = "PASS" if score_pct >= 80 else "FAIL"
        tags = test.get("tags", [])
        pipeline = test.get("pipeline", ["author"])
        skill_scores = test.get("skill_scores", {})
        pipeline_results = test.get("pipeline_results", {})

        # Load artifacts from disk
        test_data = {}
        if run_dir:
            test_data = load_test_data(run_dir, test_id)

        # Load verdicts
        verdicts = test.get("assertions_results", [])
        if not isinstance(verdicts, list):
            print(f"  WARNING: {test_id} has assertions_results as string, falling back to verdicts.json", file=sys.stderr)
            verdicts = test_data.get("verdicts", [])

        # Load agent file content
        agent_content = test.get("agent_file_content", "") or test_data.get("agent_file_content", "")

        # Load conversations and scenarios
        conversations = test.get("conversations", []) or test_data.get("conversations", {})
        scenarios = test.get("scenarios", {}) or test_data.get("scenarios", {})

        # Load spec
        spec_content = test.get("spec_content", "") or test_data.get("spec_content", "")

        html += f"""<div class="test-case">
  <div class="test-case-header">
    <div>
      <h3>{escape_html(test_id)}</h3>
      <span class="test-case-id">Pipeline: {' &rarr; '.join(pipeline)} &mdash; {status}</span>
      {''.join(f'<span class="tag">{escape_html(t)}</span>' for t in tags)}
    </div>
    <div style="text-align:right">
      <div style="font-size:24px; font-weight:700">{score_pct}%</div>
      <span class="grade-badge" style="background:{grade_color(score_pct)}">{grade_letter(score_pct)}</span>
      <div style="font-size:11px; color:var(--muted); margin-top:2px">{sum(1 for v in verdicts if v.get('result') == 'PASS')}/{len(verdicts)} assertions</div>
    </div>
  </div>
"""

        # Pipeline visualization
        html += render_pipeline_viz(test)

        # Per-skill insight cards — only show skills that have actual scores
        skills_with_scores = [s for s in pipeline if skill_scores.get(s, {}).get("dimensions")]
        extra_with_scores = [s for s in EXTRA_RUBRIC_SKILLS if skill_scores.get(s, {}).get("dimensions")]
        if skills_with_scores or extra_with_scores:
            html += '<h3 style="margin: 16px 0 8px">Skill Insights &amp; Dimensions</h3>\n'
            for skill in skills_with_scores:
                ss = skill_scores.get(skill, {})
                inv = test_data.get(f"{skill}_invocation", {})
                html += render_skill_insights(skill, ss, verdicts, inv)

            for skill in extra_with_scores:
                ss = skill_scores.get(skill, {})
                html += render_skill_insights(skill, ss, verdicts, {})

        # Count conversations
        conv_count = 0
        if isinstance(conversations, dict):
            conv_count = len(conversations.get("utterances", []))
        elif isinstance(conversations, list):
            conv_count = len(conversations)
        sc_list = scenarios.get("scenarios", scenarios) if isinstance(scenarios, dict) else scenarios
        scenario_count = len(sc_list) if isinstance(sc_list, list) else 0
        conv_label = f"Conversations ({conv_count})" if conv_count else f"Conversations ({scenario_count} scenarios)" if scenario_count else "Conversations"

        # Tabs
        html += f"""  <div class="tab-container">
    <div class="tab-buttons">
      <button class="tab-btn active" onclick="showTab('{tab_id}', 'verdicts')">Assertions ({len(verdicts)})</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'spec')">Spec</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'agent')">Agent File</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'conversations')">{conv_label}</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'deploy')">Deploy</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'scaffold')">Scaffold</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'optimize')">Optimize</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'discover')">Discover</button>
      <button class="tab-btn" onclick="showTab('{tab_id}', 'errors')">Errors</button>
    </div>
"""

        # Verdicts tab
        html += f'    <div id="{tab_id}-verdicts" class="tab-panel active">\n'
        if verdicts:
            html += '      <div class="table-wrap"><table class="verdicts-table">\n'
            html += '        <thead><tr><th>Label</th><th>Type</th><th>Result</th><th>Conf</th><th>Reason</th><th>Evidence</th></tr></thead>\n'
            html += '        <tbody>\n'
            for v in verdicts:
                html += '        ' + render_verdict_row(v) + '\n'
            html += '        </tbody>\n      </table></div>\n'
        else:
            html += '      <p style="color:var(--muted)">No verdicts recorded.</p>\n'
        html += '    </div>\n'

        # Spec tab
        html += f'    <div id="{tab_id}-spec" class="tab-panel">\n'
        if spec_content:
            html += f'      <div style="font-size:12px; line-height:1.6; max-height:600px; overflow-y:auto; padding:12px; background:var(--bg); border:1px solid var(--border); border-radius:6px"><div id="{tab_id}-spec-md">{escape_html(spec_content)}</div></div>\n'
            html += f'      <script>document.getElementById("{tab_id}-spec-md").innerHTML = typeof marked !== "undefined" ? marked.parse(document.getElementById("{tab_id}-spec-md").textContent) : document.getElementById("{tab_id}-spec-md").innerHTML.replace(/\\n/g, "<br>");</script>\n'
        else:
            html += '      <p style="color:var(--muted)">No spec file. Spec will be auto-generated from prompt on next run.</p>\n'
        html += '    </div>\n'

        # Agent file tab
        html += f'    <div id="{tab_id}-agent" class="tab-panel">\n'
        if agent_content:
            agent_name = test_data.get("agent_file_name", "Agent.agent")
            html += f'      <p style="font-size:12px; margin-bottom:8px"><strong>{escape_html(agent_name)}</strong> ({len(agent_content.splitlines())} lines)</p>\n'
            html += '      ' + render_agent_file(agent_content) + '\n'
        else:
            html += '      <p style="color:var(--muted)">No .agent file captured.</p>\n'
        html += '    </div>\n'

        # Conversations tab (smoke tests + scenarios)
        html += f'    <div id="{tab_id}-conversations" class="tab-panel">\n'
        html += '      ' + render_conversation(conversations) + '\n'
        html += '      ' + render_scenarios(scenarios) + '\n'
        html += '    </div>\n'

        # Deploy tab
        deploy_inv = test_data.get("deploy_invocation", pipeline_results.get("deploy", {}))
        deploy_files = test_data.get("deploy_files", [])
        html += f'    <div id="{tab_id}-deploy" class="tab-panel">\n'
        if deploy_inv:
            steps = deploy_inv.get("steps", {})
            html += '      <div class="table-wrap"><table class="stats-table">\n'
            html += f'        <tr><td>Status</td><td><span class="tag tag-{"success" if deploy_inv.get("status") == "success" else "fail"}">{escape_html(str(deploy_inv.get("status", "")))}</span></td></tr>\n'
            if deploy_inv.get("org"):
                html += f'        <tr><td>Org</td><td>{escape_html(str(deploy_inv["org"]))}</td></tr>\n'
            # Nested format: steps.deploy_metadata.components_deployed
            dm = steps.get("deploy_metadata", {})
            if dm:
                html += f'        <tr><td>Components</td><td>{dm.get("components_deployed", "?")}/{dm.get("components_total", "?")}</td></tr>\n'
                if dm.get("note"):
                    html += f'        <tr><td>Note</td><td>{escape_html(dm["note"])}</td></tr>\n'
            elif deploy_inv.get("components") is not None:
                # Flat format from pipeline_results
                html += f'        <tr><td>Components</td><td>{deploy_inv["components"]}</td></tr>\n'
            pub = steps.get("publish", {})
            if pub:
                html += f'        <tr><td>Publish</td><td><span class="tag tag-{"success" if pub.get("status") == "success" else "fail"}">{escape_html(pub.get("status", ""))}</span> {escape_html(pub.get("bot_developer_name", ""))}</td></tr>\n'
            elif deploy_inv.get("publish_status"):
                html += f'        <tr><td>Publish</td><td><span class="tag tag-success">{escape_html(deploy_inv["publish_status"])}</span></td></tr>\n'
            act = steps.get("activate", {})
            if act:
                html += f'        <tr><td>Activate</td><td><span class="tag tag-{"success" if act.get("status") == "success" else "fail"}">{escape_html(act.get("status", ""))}</span></td></tr>\n'
            elif deploy_inv.get("activate_status"):
                html += f'        <tr><td>Activate</td><td><span class="tag tag-success">{escape_html(deploy_inv["activate_status"])}</span></td></tr>\n'
            if deploy_inv.get("start_time"):
                html += f'        <tr><td>Duration</td><td>{escape_html(deploy_inv.get("start_time", ""))} &rarr; {escape_html(deploy_inv.get("end_time", ""))}</td></tr>\n'
            html += '      </table></div>\n'

            # Issues encountered
            issues = deploy_inv.get("issues_encountered", [])
            if issues:
                html += '<h4 style="margin:12px 0 6px; font-size:13px">Issues Encountered</h4>\n'
                for issue in issues:
                    if isinstance(issue, dict):
                        sev = issue.get("severity", "")
                        tag_cls = "tag-fail" if sev == "ERROR" else "tag-warn"
                        html += f'<div class="insight-box insight-finding" style="margin-bottom:4px"><span class="tag {tag_cls}">{escape_html(sev)}</span> {escape_html(issue.get("description", ""))}</div>\n'

            # Deploy files
            if deploy_files:
                html += '<details style="margin-top:12px"><summary>Deployed files ({} files)</summary>\n'.format(len(deploy_files))
                html += render_file_tree(deploy_files, "Deployed Files")
                html += '</details>\n'
        else:
            html += '      <p style="color:var(--muted)">No deploy data captured.</p>\n'
        html += '    </div>\n'

        # Scaffold tab
        scaffold_inv = test_data.get("scaffold_invocation", pipeline_results.get("scaffold", {}))
        scaffold_files = test_data.get("scaffold_files", [])
        html += f'    <div id="{tab_id}-scaffold" class="tab-panel">\n'
        if scaffold_inv:
            status = scaffold_inv.get("status", "")
            status_cls = "success" if status == "success" else "warn" if status == "skipped" else "fail"
            html += '      <div class="table-wrap"><table class="stats-table">\n'
            html += f'        <tr><td>Status</td><td><span class="tag tag-{status_cls}">{escape_html(str(status))}</span></td></tr>\n'
            if scaffold_inv.get("reason"):
                html += f'        <tr><td>Reason</td><td>{escape_html(scaffold_inv["reason"])}</td></tr>\n'
            if scaffold_inv.get("files_generated") is not None:
                html += f'        <tr><td>Files Generated</td><td>{scaffold_inv["files_generated"]}</td></tr>\n'
            if scaffold_inv.get("org"):
                html += f'        <tr><td>Org</td><td>{escape_html(str(scaffold_inv["org"]))}</td></tr>\n'
            targets = scaffold_inv.get("targets_scaffolded", [])
            if targets:
                html += f'        <tr><td>Targets</td><td>'
                for t in targets:
                    if isinstance(t, dict):
                        html += f'<span class="tag">{escape_html(t.get("target", ""))}</span> '
                html += '</td></tr>\n'
            if scaffold_inv.get("permissionset"):
                html += f'        <tr><td>PermissionSet</td><td><code>{escape_html(scaffold_inv["permissionset"])}</code></td></tr>\n'
            if scaffold_inv.get("start_time"):
                html += f'        <tr><td>Duration</td><td>{escape_html(scaffold_inv.get("start_time", ""))} &rarr; {escape_html(scaffold_inv.get("end_time", ""))}</td></tr>\n'
            html += '      </table></div>\n'

            if scaffold_files:
                html += '<div style="margin-top:12px">\n'
                html += render_file_tree(scaffold_files, "Scaffolded Files")
                html += '</div>\n'
        else:
            html += '      <p style="color:var(--muted)">No scaffold data captured.</p>\n'
        html += '    </div>\n'

        # Optimize tab — prefer disk invocation.json (richer data) over inline pipeline_results
        optimize_inv_disk = test_data.get("optimize_invocation", {})
        optimize_inv_inline = pipeline_results.get("optimize", {})
        # Merge: disk data takes precedence, but fill in missing fields from inline
        optimize_inv = {**optimize_inv_inline, **optimize_inv_disk} if optimize_inv_disk else optimize_inv_inline
        html += f'    <div id="{tab_id}-optimize" class="tab-panel">\n'
        html += render_optimize_details(optimize_inv)
        html += '    </div>\n'

        # Discover tab
        discover_inv = test_data.get("discover_invocation", pipeline_results.get("discover", {}))
        html += f'    <div id="{tab_id}-discover" class="tab-panel">\n'
        if discover_inv:
            found_count = discover_inv.get("targets_found", "?")
            missing_count = discover_inv.get("targets_missing", "?")
            total = discover_inv.get("total_targets", "?")
            if total == "?" and found_count != "?" and missing_count != "?":
                total = (found_count or 0) + (missing_count or 0)
            html += '      <div class="table-wrap"><table class="stats-table">\n'
            html += f'        <tr><td>Status</td><td><span class="tag tag-{"success" if discover_inv.get("status") == "success" else "fail"}">{escape_html(str(discover_inv.get("status", "")))}</span></td></tr>\n'
            html += f'        <tr><td>Total Targets</td><td>{total}</td></tr>\n'
            html += f'        <tr><td>Found</td><td>{found_count}</td></tr>\n'
            html += f'        <tr><td>Missing</td><td>{missing_count}</td></tr>\n'
            if discover_inv.get("start_time"):
                html += f'        <tr><td>Duration</td><td>{escape_html(discover_inv.get("start_time", ""))} &rarr; {escape_html(discover_inv.get("end_time", ""))}</td></tr>\n'
            html += '      </table></div>\n'
            missing = discover_inv.get("missing_targets", [])
            if missing:
                html += '<h4 style="margin:12px 0 6px; font-size:13px">Missing Targets</h4>\n'
                html += '<div style="font-family:monospace; font-size:11px">\n'
                for t in missing:
                    html += f'  <div><span class="tag tag-fail">MISSING</span> {escape_html(t)}</div>\n'
                html += '</div>\n'
            found = discover_inv.get("found_targets", [])
            if found:
                html += '<h4 style="margin:12px 0 6px; font-size:13px">Found Targets</h4>\n'
                html += '<div style="font-family:monospace; font-size:11px">\n'
                for t in found:
                    html += f'  <div><span class="tag tag-success">FOUND</span> {escape_html(t)}</div>\n'
                html += '</div>\n'
        else:
            html += '      <p style="color:var(--muted)">No discover data captured.</p>\n'
        html += '    </div>\n'

        # Errors tab
        html += f'    <div id="{tab_id}-errors" class="tab-panel">\n'
        has_errors = False
        for step_name in pipeline:
            step_result = pipeline_results.get(step_name, {})
            step_errors = step_result.get("errors", "")
            if step_errors:
                has_errors = True
                html += f'      <h4 style="margin:8px 0 4px">{escape_html(step_name.capitalize())}</h4>\n'
                html += f'      <pre class="log-content">{escape_html(step_errors)}</pre>\n'
            # Also check invocation data for issues
            inv = test_data.get(f"{step_name}_invocation", {})
            issues = inv.get("issues_encountered", [])
            if issues:
                has_errors = True
                html += f'      <h4 style="margin:8px 0 4px">{escape_html(step_name.capitalize())} Issues</h4>\n'
                for issue in issues:
                    if isinstance(issue, dict):
                        html += f'      <div class="insight-box insight-finding" style="margin-bottom:4px">'
                        html += f'<span class="tag tag-warn">{escape_html(issue.get("severity", ""))}</span> '
                        html += f'{escape_html(issue.get("description", ""))}</div>\n'
        if not has_errors:
            html += '      <p style="color:var(--muted)">No errors recorded.</p>\n'
        html += '    </div>\n'

        html += '  </div>\n'  # tab-container
        html += '</div>\n'  # test-case

    # Skill Discovery section
    if skills_discovered:
        html += '<h2>Skill Discovery</h2>\n'
        html += '<div class="table-wrap"><table class="stats-table">\n'
        skills_tags = "".join(f'<span class="tag">{escape_html(s)}</span>' for s in skills_discovered)
        html += f'  <tr><td>Skills Found</td><td>{skills_tags}</td></tr>\n'
        # Show pipeline step → skill mapping
        step_map_rows = []
        seen_skills = set()
        for step, skill in PIPELINE_SKILL_MAP.items():
            if skill not in seen_skills:
                steps_for_skill = [s for s, sk in PIPELINE_SKILL_MAP.items() if sk == skill]
                step_map_rows.append(f'<code>{escape_html(skill)}</code>: {", ".join(steps_for_skill)}')
                seen_skills.add(skill)
        html += f'  <tr><td>Pipeline Mapping</td><td>{"<br>".join(step_map_rows)}</td></tr>\n'
        conflicts = summary.get("conflicts_detected", [])
        html += f'  <tr><td>Conflicts</td><td>{len(conflicts) if conflicts else "None"}</td></tr>\n'
        skill_routing = summary.get("skill_routing", {})
        if skill_routing:
            correct = sum(1 for r in skill_routing.values() if (r.get("correct") if isinstance(r, dict) else bool(r)))
            total = len(skill_routing)
            html += f'  <tr><td>Routing Accuracy</td><td>{correct}/{total}</td></tr>\n'
        html += '</table></div>\n'

    # Execution Summary
    html += '<h2>Execution Summary</h2>\n'
    html += '<div class="table-wrap"><table class="stats-table">\n'
    html += f'  <tr><td>Total Tests</td><td>{summary.get("total_tests", len(tests))}</td></tr>\n'
    html += f'  <tr><td>Passed Tests</td><td>{summary.get("passed_tests", 0)}</td></tr>\n'
    html += f'  <tr><td>Failed Tests</td><td>{summary.get("failed_tests", 0)}</td></tr>\n'
    html += f'  <tr><td>Total Assertions</td><td>{summary.get("total_assertions", 0)}</td></tr>\n'
    html += f'  <tr><td>Passed Assertions</td><td>{summary.get("passed_assertions", 0)}</td></tr>\n'
    html += f'  <tr><td>Failed Assertions</td><td>{summary.get("failed_assertions", 0)}</td></tr>\n'
    html += f'  <tr><td>Overall Score</td><td>{overall_pct}% ({grade_letter(overall_pct)})</td></tr>\n'
    html += '</table></div>\n'

    # Footer + JS
    html += f"""
<div class="footer">
  ADLC Eval Report &mdash; {escape_html(suite_name)} &mdash; Generated {escape_html(timestamp)}
</div>

<script>
{JS}
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Report generated: {output_path}")
    print(f"Overall: {overall_pct}% ({grade_letter(overall_pct)})")
    for t in tests:
        t_score = round(t.get("score", 0) * 100, 1)
        print(f"  {t['test_id']}: {t_score}% ({grade_letter(t_score)})")
    return overall_pct


def enrich_summary(summary, summary_path):
    """Merge judge analysis.json files into summary.json for richer report rendering.

    Looks for author/analysis.json and test/analysis.json next to the summary.json,
    then merges their insights into the summary's key_findings, spec_compliance,
    recommended_actions, and per-utterance insight/recommendation fields.

    Returns the enriched summary (also writes it back to disk).
    """
    summary_dir = Path(summary_path).parent
    changes = []

    for test in summary.get("tests", []):
        test_id = test.get("test_id", "")
        # Determine test directory — could be summary_dir itself or summary_dir/test_id
        test_dir = summary_dir / test_id if (summary_dir / test_id).exists() else summary_dir

        # Load author analysis
        author_path = test_dir / "author" / "analysis.json"
        author = load_json(author_path)
        if author:
            changes.append(f"author judge ({author.get('grade', '?')})")
            design_review = author.get("design_review", {})

            # Merge weaknesses into key_findings if not already present
            existing_titles = {f.get("title", "") for f in summary.get("key_findings", []) if isinstance(f, dict) and isinstance(f.get("title"), str)}
            for weakness in design_review.get("weaknesses", []):
                if isinstance(weakness, dict):
                    title = str(weakness.get("title", weakness.get("description", "")))
                    explanation = str(weakness.get("description", title))
                    recommendation = str(weakness.get("recommendation", ""))
                else:
                    title = str(weakness)
                    explanation = title
                    recommendation = ""
                if title and title not in existing_titles:
                    summary.setdefault("key_findings", []).append({
                        "title": title[:120],
                        "severity": "medium",
                        "explanation": explanation,
                        "recommendation": recommendation
                    })

            # Merge spec compliance mismatches
            for mismatch in author.get("spec_compliance", {}).get("mismatches", []):
                existing_reqs = {item.get("requirement", "") for item in summary.get("spec_compliance", [])}
                req = mismatch.get("requirement", "")
                if req and req not in existing_reqs:
                    summary.setdefault("spec_compliance", []).append({
                        "requirement": req,
                        "status": mismatch.get("status", "PARTIAL"),
                        "notes": mismatch.get("notes", "")
                    })

            # Merge risks into key_findings
            for risk in design_review.get("risks", []):
                if isinstance(risk, dict):
                    title = str(risk.get("title", risk.get("description", "")))
                    explanation = str(risk.get("description", title))
                    recommendation = str(risk.get("recommendation", ""))
                    severity = str(risk.get("severity", "low"))
                else:
                    title = str(risk)
                    explanation = title
                    recommendation = ""
                    severity = "low"
                if title and title not in existing_titles:
                    summary.setdefault("key_findings", []).append({
                        "title": title[:120],
                        "severity": severity,
                        "explanation": explanation,
                        "recommendation": recommendation
                    })

        # Load test analysis
        test_analysis_path = test_dir / "test" / "analysis.json"
        test_analysis = load_json(test_analysis_path)
        if test_analysis:
            utt_results = test_analysis.get("utterance_results", [])
            changes.append(f"test judge ({len(utt_results)} utterances)")

            # Merge per-utterance insights into conversations
            for utt_a in utt_results:
                utt_text = utt_a.get("utterance", "")
                for conv_utt in test.get("conversations", {}).get("utterances", []):
                    if conv_utt.get("utterance") == utt_text:
                        for field in ("insight", "recommendation", "root_cause", "response_quality"):
                            if utt_a.get(field):
                                conv_utt[field] = utt_a[field]
                        break

            # Merge test judge key findings
            existing_titles = {f.get("title", "") for f in summary.get("key_findings", []) if isinstance(f, dict) and isinstance(f.get("title"), str)}
            for finding in test_analysis.get("key_findings", []):
                if isinstance(finding, str) and finding not in existing_titles:
                    summary.setdefault("key_findings", []).append({
                        "title": finding[:120], "severity": "info",
                        "explanation": finding, "recommendation": ""
                    })
                elif isinstance(finding, dict) and finding.get("title", "") not in existing_titles:
                    summary.setdefault("key_findings", []).append(finding)

            # Merge test judge recommendations
            for rec in test_analysis.get("recommendations", []):
                existing_actions = {a.get("action", "") for a in summary.get("recommended_actions", [])}
                if isinstance(rec, str) and rec not in existing_actions:
                    summary.setdefault("recommended_actions", []).append({
                        "priority": "P2", "action": rec, "effort": "", "impact": ""
                    })
                elif isinstance(rec, dict) and rec.get("action", "") not in existing_actions:
                    summary.setdefault("recommended_actions", []).append(rec)

    if changes:
        # Write enriched summary back
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Enriched summary with: {', '.join(changes)}")
        kf = len(summary.get("key_findings", []))
        sc = len(summary.get("spec_compliance", []))
        ra = len(summary.get("recommended_actions", []))
        utt_insights = sum(
            1 for t in summary.get("tests", [])
            for u in t.get("conversations", {}).get("utterances", [])
            if u.get("insight")
        )
        print(f"  {kf} findings, {sc} spec items, {ra} actions, {utt_insights} utterance insights")
    else:
        print("No judge analysis files found — report will use existing summary data")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Generate interactive HTML report from ADLC eval summary.json"
    )
    parser.add_argument("summary", help="Path to summary.json from eval run")
    parser.add_argument("--output", "-o", help="Output HTML path (default: report.html in same dir)")
    parser.add_argument("--compare", help="Path to previous summary.json for comparison")
    parser.add_argument("--enrich", action="store_true",
                        help="Merge judge analysis.json files into summary before generating report")
    args = parser.parse_args()

    summary = load_json(args.summary)

    if args.enrich:
        summary = enrich_summary(summary, args.summary)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(args.summary).parent / "report.html"

    compare = None
    if args.compare:
        compare = load_json(args.compare)

    generate_report(summary, output_path, compare, summary_path=args.summary)


if __name__ == "__main__":
    main()
