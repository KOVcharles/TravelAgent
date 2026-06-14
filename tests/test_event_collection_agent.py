from pathlib import Path

from agents.lazy_agent_registry import LazyAgentRegistry


def test_event_collection_skill_is_registered():
    registry = LazyAgentRegistry(model=None, cache={})

    assert "event_collection" in registry
    assert "event-collection" in registry.keys()


def test_event_collection_skill_has_agent_script():
    script_path = Path(".claude/skills/event-collection/script/agent.py")

    assert script_path.exists()
