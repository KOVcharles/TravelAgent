"""Fast rule-based intent routing before LLM intent recognition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.intent_guard import (
    GuardResult,
    can_call_information_query,
    guard_user_input,
    passes_confidence_gate,
)
from core.intent_catalog import CHITCHAT_EXACT, CHITCHAT_KEYWORDS


@dataclass(frozen=True)
class IntentRoute:
    intent_type: str
    agent_schedule: List[Dict[str, Any]]
    confidence: float
    reason: str
    key_entities: Dict[str, Any]
    should_call_skill: bool = True

    def to_intention_data(self, user_query: str) -> Dict[str, Any]:
        return {
            "routing": {
                "intent": self.intent_type,
                "confidence": self.confidence,
                "reason": self.reason,
                "should_call_skill": self.should_call_skill,
            },
            "reasoning": f"Fast intent router: {self.reason}",
            "intents": [
                {
                    "type": self.intent_type,
                    "confidence": self.confidence,
                    "description": self.reason,
                    "reason": self.reason,
                    "should_call_skill": self.should_call_skill,
                }
            ],
            "key_entities": self.key_entities,
            "rewritten_query": user_query,
            "agent_schedule": self.agent_schedule if self.should_call_skill else [],
        }


class FastIntentRouter:
    """Cheap high-confidence router for common user requests."""

    POLICY_KEYWORDS = (
        "标准", "报销", "差旅政策", "住宿标准", "补贴", "流程",
        "餐补", "餐费", "餐饮", "饭补", "补助", "津贴",
        "住宿费", "交通费", "差旅费", "发票",
    )
    WEATHER_KEYWORDS = ("天气", "气温", "下雨", "预报")
    SEARCH_KEYWORDS = ("查一下", "搜索", "查询", "了解一下")
    MEMORY_KEYWORDS = ("我去过", "我的历史", "我之前", "上次", "我的偏好", "我喜欢去哪")
    PREFERENCE_KEYWORDS = ("我喜欢", "我常坐", "我常住", "我住在", "我家在", "我偏好", "我习惯", "我不喜欢")
    TRIP_KEYWORDS = ("我要去", "我想去", "帮我规划", "帮我安排", "规划行程", "安排行程", "从")

    @classmethod
    def route(cls, user_query: str) -> Optional[IntentRoute]:
        q = (user_query or "").strip()
        q_lower = q.lower()
        if not q:
            return None

        guard_result = guard_user_input(q)
        if guard_result:
            return cls._from_guard_result(guard_result)

        if q_lower in CHITCHAT_EXACT or q in CHITCHAT_EXACT or any(keyword in q for keyword in CHITCHAT_KEYWORDS):
            return cls._single("chitchat", "chitchat", 0.99, "明确的寒暄或社交对话")

        if any(keyword in q for keyword in cls.MEMORY_KEYWORDS):
            return cls._single("memory_query", "memory_query", 0.9, "询问用户自己的历史或偏好记忆")

        if any(keyword in q for keyword in cls.PREFERENCE_KEYWORDS):
            return cls._single("preference", "preference", 0.9, "表达或更新用户偏好")

        if any(keyword in q for keyword in cls.POLICY_KEYWORDS):
            return cls._single("rag_knowledge", "rag_knowledge", 0.88, "查询差旅制度、标准或报销政策")

        if any(keyword in q for keyword in cls.WEATHER_KEYWORDS):
            info_guard = can_call_information_query(q, 0.9)
            return cls._from_guard_result(info_guard)

        if cls._looks_like_trip_request(q):
            return IntentRoute(
                intent_type="itinerary_planning",
                confidence=0.88,
                reason="明确的行程规划或出行意图",
                key_entities={},
                agent_schedule=[
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
            )

        if any(keyword in q for keyword in cls.SEARCH_KEYWORDS):
            info_guard = can_call_information_query(q, 0.82)
            return cls._from_guard_result(info_guard)

        return None

    @classmethod
    def _single(cls, intent_type: str, agent_name: str, confidence: float, reason: str) -> IntentRoute:
        return IntentRoute(
            intent_type=intent_type,
            confidence=confidence,
            reason=reason,
            key_entities={},
            agent_schedule=[
                {
                    "agent_name": agent_name,
                    "priority": 1,
                    "reason": reason,
                    "expected_output": "完成用户请求",
                }
            ],
        )

    @classmethod
    def _from_guard_result(cls, result: GuardResult) -> IntentRoute:
        return IntentRoute(
            intent_type=result.intent,
            confidence=result.confidence,
            reason=result.reason,
            key_entities={},
            agent_schedule=result.agent_schedule,
            should_call_skill=result.should_call_skill and passes_confidence_gate(result.intent, result.confidence),
        )

    @classmethod
    def _looks_like_trip_request(cls, query: str) -> bool:
        if any(keyword in query for keyword in cls.TRIP_KEYWORDS):
            if "从" in query and ("到" in query or "去" in query):
                return True
            return any(keyword in query for keyword in ("去", "规划", "行程", "出差", "旅游"))
        return False
