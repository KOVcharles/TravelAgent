"""Fast rule-based intent routing before LLM intent recognition."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.schedule_builder import build_agent_schedule
from core.intent_guard import (
    GuardResult,
    can_call_information_query,
    guard_user_input,
    has_business_travel_context,
    passes_confidence_gate,
)
from core.intent_catalog import CHITCHAT_EXACT, CHITCHAT_KEYWORDS


@dataclass(frozen=True)
class IntentCandidate:
    type: str
    confidence: float
    reason: str
    source: str = "rule"


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
        "报销", "差旅政策", "住宿标准", "补贴",
        "餐补", "餐费", "餐饮", "饭补", "补助", "津贴",
        "住宿费", "交通费", "差旅费", "发票",
    )
    GENERIC_POLICY_KEYWORDS = ("标准", "流程")
    WEATHER_KEYWORDS = ("天气", "气温", "下雨", "预报")
    SEARCH_KEYWORDS = ("查一下", "搜索", "查询", "了解一下")
    COMPLIANCE_KEYWORDS = ("合规", "符合标准", "检查行程", "行程检查", "是否超标")
    MEMORY_KEYWORDS = ("我去过", "我的差旅", "差旅记录", "出差记录", "上次出差", "过去行程", "我的出行偏好")
    PREFERENCE_KEYWORDS = ("我喜欢", "我常坐", "我常住", "我住在", "我家在", "我偏好", "我习惯", "我不喜欢")
    TRIP_KEYWORDS = (
        "帮我规划", "帮我安排", "规划行程", "安排行程", "规划路线", "出行方案",
        "怎么走最好", "路线怎么走", "从",
    )

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

        candidates = cls.detect(q)
        if candidates:
            intents = [
                {
                    "type": candidate.type,
                    "confidence": candidate.confidence,
                    "description": candidate.reason,
                    "reason": candidate.reason,
                    "should_call_skill": passes_confidence_gate(candidate.type, candidate.confidence),
                }
                for candidate in candidates
            ]
            callable_intents = [item for item in intents if item["should_call_skill"]]
            primary = callable_intents[0] if callable_intents else intents[0]
            return IntentRoute(
                intent_type=primary["type"],
                confidence=primary["confidence"],
                reason=primary["reason"],
                key_entities={},
                agent_schedule=build_agent_schedule(callable_intents),
                should_call_skill=bool(callable_intents),
            )

        return None

    @classmethod
    def detect(cls, user_query: str) -> List[IntentCandidate]:
        """Collect rule-based business intent candidates without first-match exit."""
        q = (user_query or "").strip()
        if not q:
            return []

        candidates: List[IntentCandidate] = []

        has_policy = any(keyword in q for keyword in cls.POLICY_KEYWORDS) or (
            any(keyword in q for keyword in cls.GENERIC_POLICY_KEYWORDS)
            and has_business_travel_context(q)
        )
        has_weather = any(keyword in q for keyword in cls.WEATHER_KEYWORDS)
        has_search = any(keyword in q for keyword in cls.SEARCH_KEYWORDS)
        has_compliance = any(keyword in q for keyword in cls.COMPLIANCE_KEYWORDS)

        if any(keyword in q for keyword in cls.MEMORY_KEYWORDS):
            candidates.append(IntentCandidate("memory_query", 0.9, "询问用户自己的历史或偏好记忆"))

        if any(keyword in q for keyword in cls.PREFERENCE_KEYWORDS):
            candidates.append(IntentCandidate("preference", 0.9, "表达或更新用户偏好"))

        if has_policy:
            candidates.append(IntentCandidate("rag_knowledge", 0.88, "查询差旅制度、标准或报销政策"))

        if has_compliance:
            candidates.append(IntentCandidate("trip_compliance", 0.9, "依据公司制度检查差旅行程合规性"))

        if has_weather:
            info_guard = can_call_information_query(q, 0.9)
            if info_guard.intent == "information_query" and info_guard.should_call_skill:
                candidates.append(IntentCandidate("information_query", info_guard.confidence, info_guard.reason))

        if cls._looks_like_trip_request(q):
            candidates.append(IntentCandidate("itinerary_planning", 0.88, "明确的行程规划或出行意图"))

        # Generic search verbs like “查一下” should not turn policy/RAG queries
        # such as “查一下出差补贴” into an external information_query.
        if has_search and not has_policy and not has_compliance:
            info_guard = can_call_information_query(q, 0.82)
            if info_guard.intent == "information_query" and info_guard.should_call_skill:
                candidates.append(IntentCandidate("information_query", info_guard.confidence, info_guard.reason))

        return cls._dedupe_candidates(candidates)

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
    def _dedupe_candidates(cls, candidates: List[IntentCandidate]) -> List[IntentCandidate]:
        by_type: Dict[str, IntentCandidate] = {}
        order: List[str] = []
        for candidate in candidates:
            existing = by_type.get(candidate.type)
            if existing is None:
                by_type[candidate.type] = candidate
                order.append(candidate.type)
            elif candidate.confidence > existing.confidence:
                by_type[candidate.type] = candidate
        return [by_type[intent_type] for intent_type in order]

    @classmethod
    def _looks_like_trip_request(cls, query: str) -> bool:
        if not has_business_travel_context(query):
            return False
        if any(keyword in query for keyword in cls.TRIP_KEYWORDS):
            if "从" in query and ("到" in query or "去" in query):
                return True
            return any(keyword in query for keyword in ("去", "规划", "安排", "行程", "路线", "出差", "差旅"))
        return False
