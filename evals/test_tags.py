"""
Master list of test tags for ADLC eval test suites.

IMPORTANT DISTINCTION:
- Assertion labels = HORIZONTAL CAPABILITIES (skills being tested)
- Test tags = VERTICAL EXPERTISE (domain/industry the test is in)

Test tags describe WHAT DOMAIN the test is in, not what capability.
For example:
  - An HR agent that needs verification uses tags: ["hr-agent", "verification-gate"]
  - The verification capability is tested via [fsm:verification-gate] assertion

Tags are used in test cases to categorize and filter tests.
"""

from typing import Optional

# =============================================================================
# DOMAIN TAGS - Industry/Use-Case Verticals
# =============================================================================

DOMAIN_TAGS = {
    # Customer-facing
    "customer-service": "General customer support — order status, returns, FAQs",
    "retail": "E-commerce and retail — product search, order tracking, inventory",
    "financial-services": "Banking, insurance, investments — account inquiries, claims",
    "healthcare": "Medical and healthcare — appointment scheduling, triage, info",
    "real-estate": "Property search, tour scheduling, mortgage info",
    "travel": "Booking, itineraries, travel support",
    "telecommunications": "Service inquiries, billing, technical support",

    # Internal/Employee
    "hr-agent": "Human resources — PTO requests, policy questions, onboarding",
    "it-support": "IT helpdesk — password resets, ticket creation, troubleshooting",
    "sales-agent": "Sales and lead qualification — product inquiries, lead capture",
    "legal-intake": "Legal case intake — initial consultation, document collection",

    # Knowledge/Info
    "faq-bot": "Knowledge retrieval — company FAQs, documentation, help articles",
    "knowledge-base": "Structured knowledge retrieval with citations",
}

# =============================================================================
# PATTERN TAGS - FSM and Architectural Patterns
# =============================================================================

PATTERN_TAGS = {
    "multi-topic": "Hub-and-spoke pattern with multiple specialized topics",
    "verification-gate": "Identity verification pattern before sensitive operations",
    "linear-flow": "Step-by-step guided flow pattern",
    "single-topic": "Simple single-topic agent without routing",
    "escalation-heavy": "Agent with significant escalation paths",
}

# =============================================================================
# COMPLEXITY TAGS - Test Difficulty Levels
# =============================================================================

COMPLEXITY_TAGS = {
    "minimal": "Basic structure — hello world, simple FAQ",
    "easy": "Simple agent with clear requirements",
    "medium": "Multiple topics, some action chaining",
    "hard": "Complex FSM, verification gates, multiple action chains",
}

# =============================================================================
# FEATURE TAGS - Specific Features Being Tested
# =============================================================================

FEATURE_TAGS = {
    "action-chaining": "Multiple actions that depend on each other",
    "slot-filling": "Conversational data collection (...)",
    "after-reasoning": "Post-LLM deterministic actions",
    "conditional-logic": "Complex if/else branching",
    "cross-topic-vars": "Variables shared across topics",
    "retriever-actions": "Data Cloud retriever actions",
    "apex-actions": "Apex InvocableMethod actions",
    "flow-actions": "Salesforce Flow actions",
}

# =============================================================================
# SAFETY TAGS - Safety-Focused Test Categories
# =============================================================================

SAFETY_TAGS = {
    "safety-critical": "Tests focused on safety and responsible AI",
    "pii-handling": "Tests involving PII collection and handling",
    "regulated-domain": "Regulated domains (finance, health, legal)",
    "crisis-scenarios": "Tests involving crisis or emergency scenarios",
}

# =============================================================================
# COMBINED EXPORTS
# =============================================================================

ALL_TAGS = {
    **DOMAIN_TAGS,
    **PATTERN_TAGS,
    **COMPLEXITY_TAGS,
    **FEATURE_TAGS,
    **SAFETY_TAGS,
}

# Array of all valid tag strings
VALID_TAGS: list[str] = list(ALL_TAGS.keys())


def is_valid_tag(tag: str) -> bool:
    """Check if a string is a valid test tag."""
    return tag in ALL_TAGS


def get_tag_description(tag: str) -> Optional[str]:
    """Get the description for a tag."""
    return ALL_TAGS.get(tag)


def get_tag_category(tag: str) -> Optional[str]:
    """
    Infer the category a tag belongs to.
    Returns: 'domain', 'pattern', 'complexity', 'feature', or 'safety'
    """
    if tag in DOMAIN_TAGS:
        return "domain"
    if tag in PATTERN_TAGS:
        return "pattern"
    if tag in COMPLEXITY_TAGS:
        return "complexity"
    if tag in FEATURE_TAGS:
        return "feature"
    if tag in SAFETY_TAGS:
        return "safety"
    return None


def validate_tags(tags: list[str]) -> dict:
    """
    Validate a list of tags.
    Returns { valid: True, tags: [...] } or { valid: False, invalid_tags: [...] }
    """
    invalid = [t for t in tags if not is_valid_tag(t)]
    if invalid:
        return {"valid": False, "invalid_tags": invalid}
    return {"valid": True, "tags": tags}


def get_tags_by_category(category: str) -> dict[str, str]:
    """Get all tags in a specific category."""
    category_map = {
        "domain": DOMAIN_TAGS,
        "pattern": PATTERN_TAGS,
        "complexity": COMPLEXITY_TAGS,
        "feature": FEATURE_TAGS,
        "safety": SAFETY_TAGS,
    }
    return category_map.get(category, {})


# Category summaries for documentation
TAG_CATEGORIES = {
    "domain": "Industry/use-case verticals (customer-service, hr-agent, etc.)",
    "pattern": "FSM and architectural patterns (multi-topic, verification-gate, etc.)",
    "complexity": "Test difficulty levels (minimal, easy, medium, hard)",
    "feature": "Specific features being tested (action-chaining, slot-filling, etc.)",
    "safety": "Safety-focused test categories (safety-critical, pii-handling, etc.)",
}
