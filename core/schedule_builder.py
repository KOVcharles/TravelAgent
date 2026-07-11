"""Build executable agent schedules from callable intents."""
from __future__ import annotations

from typing import Any, Dict, List

from utils.skill_loader import SkillLoader


def _load_schedule_rules() -> Dict[str, List[Dict[str, Any]]]:
    rules: Dict[str, List[Dict[str, Any]]] = {}
    for manifest in SkillLoader().load_manifests().values():
        if not manifest.intent:
            continue
        rules[manifest.intent] = [step.model_dump() for step in manifest.execution]
    return rules


SCHEDULE_RULES = _load_schedule_rules()


def build_agent_schedule(intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert callable intents into a deduped, priority-sorted agent schedule."""
    by_agent: Dict[str, Dict[str, Any]] = {}

    for intent in intents:
        intent_type = intent.get("type")
        if not intent_type:
            continue

        for item in SCHEDULE_RULES.get(intent_type, []):
            agent_name = item["agent_name"]
            existing = by_agent.get(agent_name)
            if existing is None or item["priority"] < existing["priority"]:
                runtime_item = dict(item)
                runtime_item.pop("skill", None)
                by_agent[agent_name] = runtime_item

    return sorted(by_agent.values(), key=lambda item: item.get("priority", 999))
