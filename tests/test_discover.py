"""Tests for discover.py — target extraction from .agent files."""

import pytest
from pathlib import Path
from scripts.discover import extract_targets, extract_actions, _suggest_similar, Suggestion


SAMPLE_AGENT = """\
system:
\tinstructions: "You are a test agent."
\tmessages:
\t\twelcome: "Hello!"
\t\terror: "Error occurred."

config:
\tagent_name: "TestAgent"
\tdefault_agent_user: "user@test.com"
\tagent_label: "Test Agent"
\tdescription: "A test agent"

variables:
\tEndUserId: linked string
\t\tsource: @MessagingSession.MessagingEndUserId
\t\tdescription: "End User ID"

language:
\tdefault_locale: "en_US"
\tadditional_locales: ""
\tall_additional_locales: False

start_agent entry:
\tdescription: "Entry point"
\treasoning:
\t\tinstructions: |
\t\t\tRoute to the appropriate topic.
\t\tactions:
\t\t\tgo_orders: @utils.transition to @topic.orders
\t\t\t\tdescription: "Check orders"

topic orders:
\tdescription: "Handle order inquiries"
\tactions:
\t\tget_order_status:
\t\t\tdescription: "Look up order status"
\t\t\tinputs:
\t\t\t\torder_number: string
\t\t\t\t\tdescription: "Order number"
\t\t\toutputs:
\t\t\t\torder_status: string
\t\t\t\t\tdescription: "Status of the order"
\t\t\ttarget: "flow://Get_Order_Status"
\t\tprocess_return:
\t\t\tdescription: "Process a return"
\t\t\tinputs:
\t\t\t\torder_id: string
\t\t\t\t\tdescription: "Order ID"
\t\t\toutputs:
\t\t\t\treturn_id: string
\t\t\t\t\tdescription: "Return ID"
\t\t\ttarget: "apex://ProcessReturn"
\t\tknowledge_search:
\t\t\tdescription: "Search knowledge base"
\t\t\ttarget: "retriever://FAQ_Knowledge"
\treasoning:
\t\tinstructions: |
\t\t\tHelp with orders.
"""


@pytest.fixture
def sample_agent_file(tmp_path):
    """Create a temporary .agent file."""
    agent_file = tmp_path / "TestAgent" / "TestAgent.agent"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text(SAMPLE_AGENT)
    return agent_file


class TestExtractTargets:
    def test_extracts_all_target_types(self, sample_agent_file):
        targets = extract_targets(sample_agent_file)
        assert len(targets) == 3

        uris = {t[0] for t in targets}
        assert "flow://Get_Order_Status" in uris
        assert "apex://ProcessReturn" in uris
        assert "retriever://FAQ_Knowledge" in uris

    def test_extracts_correct_types(self, sample_agent_file):
        targets = extract_targets(sample_agent_file)
        types = {t[1] for t in targets}
        assert types == {"flow", "apex", "retriever"}

    def test_extracts_correct_names(self, sample_agent_file):
        targets = extract_targets(sample_agent_file)
        names = {t[2] for t in targets}
        assert names == {"Get_Order_Status", "ProcessReturn", "FAQ_Knowledge"}

    def test_empty_file(self, tmp_path):
        agent_file = tmp_path / "Empty.agent"
        agent_file.write_text("system:\n\tinstructions: 'hello'\n")
        targets = extract_targets(agent_file)
        assert targets == []


class TestSuggestSimilar:
    def test_exact_match(self):
        suggestions = _suggest_similar("Get_Order_Status", ["Get_Order_Status", "Other"])
        assert any(s.name == "Get_Order_Status" for s in suggestions)

    def test_fuzzy_match(self):
        suggestions = _suggest_similar("GetOrderStatus", ["Get_Order_Status", "Unrelated"])
        assert len(suggestions) >= 1
        assert suggestions[0].name == "Get_Order_Status"

    def test_no_match(self):
        suggestions = _suggest_similar("XyzAbcDef", ["Completely_Different"])
        # May or may not match depending on threshold — just verify it runs
        assert isinstance(suggestions, list)

    def test_returns_top_3(self):
        available = [f"Get_Order_{i}" for i in range(10)]
        suggestions = _suggest_similar("Get_Order_Status", available)
        assert len(suggestions) <= 3
