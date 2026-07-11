from agents.lazy_agent_registry import LazyAgentRegistry
from utils.skill_loader import SkillLoader


EXPECTED_SKILLS = {
    "ask-question",
    "check-trip-compliance",
    "chitchat",
    "event-collection",
    "mcp-tool",
    "memory-query",
    "plan-trip",
    "preference",
    "query-info",
}


EXPECTED_LEGACY_AGENT_NAMES = {
    "rag_knowledge",
    "trip_compliance",
    "memory_query",
    "preference",
    "information_query",
    "itinerary_planning",
    "event_collection",
    "chitchat",
    "mcp_tool",
}


def test_skill_loader_discovers_runtime_skills():
    skills = SkillLoader().load_skills()

    assert set(skills) == EXPECTED_SKILLS


def test_lazy_agent_registry_exposes_skill_and_legacy_names():
    registry = LazyAgentRegistry(model=None, cache={})
    keys = set(registry.keys())

    assert EXPECTED_SKILLS.issubset(keys)
    assert EXPECTED_LEGACY_AGENT_NAMES.issubset(keys)
