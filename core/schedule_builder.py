"""Build executable agent schedules from callable intents."""
from __future__ import annotations

from typing import Any, Dict, List


SCHEDULE_RULES = {
    "chitchat": [
        {
            "agent_name": "chitchat",
            "priority": 1,
            "reason": "明确的寒暄或社交对话",
            "expected_output": "友好的社交回复",
        }
    ],
    "preference": [
        {
            "agent_name": "preference",
            "priority": 1,
            "reason": "记录或更新用户偏好",
            "expected_output": "完成用户偏好处理",
        }
    ],
    "memory_query": [
        {
            "agent_name": "memory_query",
            "priority": 1,
            "reason": "查询用户历史或偏好记忆",
            "expected_output": "完成用户记忆查询",
        }
    ],
    "rag_knowledge": [
        {
            "agent_name": "rag_knowledge",
            "priority": 1,
            "reason": "查询差旅制度、标准或报销政策",
            "expected_output": "完成政策知识查询",
        }
    ],
    "information_query": [
        {
            "agent_name": "information_query",
            "priority": 1,
            "reason": "明确的信息查询请求",
            "expected_output": "完成用户信息查询",
        }
    ],
    "event_collection": [
        {
            "agent_name": "event_collection",
            "priority": 1,
            "reason": "收集行程基础信息",
            "expected_output": "出发地、目的地、日期、行程目的和缺失信息",
        }
    ],
    "itinerary_planning": [
        {
            "agent_name": "event_collection",
            "priority": 1,
            "reason": "收集行程基础信息",
            "expected_output": "出发地、目的地、日期、行程目的和缺失信息",
        },
        {
            "agent_name": "itinerary_planning",
            "priority": 2,
            "reason": "基于收集信息生成行程规划",
            "expected_output": "结构化行程计划",
        },
    ],
}


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
                by_agent[agent_name] = dict(item)

    return sorted(by_agent.values(), key=lambda item: item.get("priority", 999))
