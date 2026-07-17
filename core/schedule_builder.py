"""Build executable agent schedules from callable intents."""
from __future__ import annotations

from typing import Any, Dict, List

from utils.skill_loader import SkillLoader


def _load_schedule_rules() -> Dict[str, List[Dict[str, Any]]]:
    rules: Dict[str, List[Dict[str, Any]]] = {}
    for definition in SkillLoader().load_definitions().values():
        if not definition.intent:
            continue
        rules[definition.intent] = [step.model_dump() for step in definition.execution]
    return rules


SCHEDULE_RULES = _load_schedule_rules()


def build_agent_schedule(intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert callable intents into a deduped, priority-sorted agent schedule."""
    by_agent: Dict[str, Dict[str, Any]] = {}
    itinerary_workflow = any(item.get("type") == "itinerary_planning" for item in intents)

    for intent in intents:
        intent_type = intent.get("type")
        if not intent_type:
            continue

        for item in SCHEDULE_RULES.get(intent_type, []):
            agent_name = item["agent_name"]
            existing = by_agent.get(agent_name)
            # A planning workflow must collect trip facts before querying policy
            # or external information.  An additional explicit policy/weather
            # intent must not pull either dependency back to priority 1.
            depends_on_trip_facts = itinerary_workflow and agent_name in {
                "rag_knowledge", "information_query",
            }
            should_replace = existing is None or (
                item["priority"] > existing["priority"]
                if depends_on_trip_facts
                else item["priority"] < existing["priority"]
            )
            if should_replace:
                runtime_item = dict(item)
                runtime_item.pop("skill", None)
                by_agent[agent_name] = runtime_item

    return sorted(by_agent.values(), key=lambda item: item.get("priority", 999))
