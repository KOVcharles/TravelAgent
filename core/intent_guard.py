"""Lightweight intent guard used before skill routing."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional

from core.intent_catalog import CHITCHAT_EXACT


DEFAULT_CONFIDENCE_THRESHOLD = 0.65
INFORMATION_QUERY_THRESHOLD = 0.75


@dataclass(frozen=True)
class GuardResult:
    intent: str
    confidence: float
    reason: str
    should_call_skill: bool
    agent_schedule: List[Dict[str, Any]] = field(default_factory=list)
    clarification: Optional[str] = None

    def to_intention_data(self, user_query: str) -> Dict[str, Any]:
        return {
            "routing": {
                "intent": self.intent,
                "confidence": self.confidence,
                "reason": self.reason,
                "should_call_skill": self.should_call_skill,
            },
            "reasoning": self.reason,
            "intents": [
                {
                    "type": self.intent,
                    "confidence": self.confidence,
                    "description": self.reason,
                    "reason": self.reason,
                    "should_call_skill": self.should_call_skill,
                }
            ],
            "key_entities": {},
            "rewritten_query": normalize_query(user_query),
            "agent_schedule": self.agent_schedule if self.should_call_skill else [],
            "clarification": self.clarification,
        }


UNCLEAR_EXACT = {
    "你", "你?", "你？", "啊", "啊?", "啊？", "嗯", "嗯?", "嗯？",
    "test", "测试", "随便看看", "看看", "查一下", "帮我查", "查询",
}
UNSUPPORTED_KEYWORDS = (
    "订票付款", "帮我付款", "代付", "支付", "转账", "删除服务器", "格式化",
)
GIBBERISH_RE = re.compile(r"^[\W_]+$")


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())


def meaningful_length(query: str) -> int:
    return len(re.findall(r"[\w\u4e00-\u9fff]", query or ""))


def guard_user_input(user_query: str) -> Optional[GuardResult]:
    q = normalize_query(user_query)
    q_lower = q.lower()
    length = meaningful_length(q)

    if not q:
        return _unclear("输入为空，缺少可识别的用户意图")

    if q_lower in CHITCHAT_EXACT or q in CHITCHAT_EXACT:
        return _chitchat()

    if q_lower in UNCLEAR_EXACT or q in UNCLEAR_EXACT:
        return _unclear("输入过短或缺少明确任务")

    if GIBBERISH_RE.match(q):
        return _unclear("输入疑似乱码或只有标点")

    if any(keyword in q for keyword in UNSUPPORTED_KEYWORDS):
        return GuardResult(
            intent="unsupported",
            confidence=0.9,
            reason="用户请求包含当前系统不支持或不应执行的操作",
            should_call_skill=False,
            clarification="这个操作我目前不能直接处理。可以帮你做差旅政策查询、行程规划或旅行信息查询。",
        )

    if length <= 2:
        return _unclear("输入太短，无法判断具体意图")

    return None


def passes_confidence_gate(intent: str, confidence: float) -> bool:
    threshold = (
        INFORMATION_QUERY_THRESHOLD
        if intent == "information_query"
        else DEFAULT_CONFIDENCE_THRESHOLD
    )
    return confidence >= threshold


def can_call_information_query(user_query: str, confidence: float) -> GuardResult:
    q = normalize_query(user_query)
    length = meaningful_length(q)

    if confidence < INFORMATION_QUERY_THRESHOLD:
        return _unclear(
            f"information_query 置信度 {confidence:.2f} 低于阈值 {INFORMATION_QUERY_THRESHOLD:.2f}"
        )

    if length < 6:
        return _unclear("信息查询输入过短，缺少明确查询对象")

    if not has_clear_information_target(q):
        return _unclear("缺少明确的信息查询对象")

    return GuardResult(
        intent="information_query",
        confidence=confidence,
        reason="明确的信息查询请求",
        should_call_skill=True,
        agent_schedule=[
            {
                "agent_name": "information_query",
                "priority": 1,
                "reason": "明确的信息查询请求",
                "expected_output": "完成用户请求",
            }
        ],
    )


def has_clear_information_target(query: str) -> bool:
    if any(keyword in query for keyword in ("天气", "气温", "下雨", "预报")):
        return meaningful_length(query) >= 6

    if any(keyword in query for keyword in ("开放时间", "门票", "航班", "高铁", "路线", "价格", "地址")):
        return True

    search_words = ("查一下", "搜索", "查询", "了解一下")
    if any(word in query for word in search_words):
        remainder = query
        for word in search_words:
            remainder = remainder.replace(word, "")
        remainder = remainder.replace("帮我", "").replace("一下", "").strip(" ，。？?！!")
        return meaningful_length(remainder) >= 4

    return False


def _unclear(reason: str) -> GuardResult:
    return GuardResult(
        intent="unclear",
        confidence=0.9,
        reason=reason,
        should_call_skill=False,
        clarification="我还不太确定你的意思。你是想查询差旅政策、规划行程，还是查某个旅行信息？",
    )


def _chitchat() -> GuardResult:
    """寒暄/社交对话：路由到 chitchat skill（skill-backed）。"""
    return GuardResult(
        intent="chitchat",
        confidence=0.99,
        reason="明确的寒暄或社交对话",
        should_call_skill=True,
        agent_schedule=[
            {
                "agent_name": "chitchat",
                "priority": 1,
                "reason": "明确的寒暄或社交对话",
                "expected_output": "友好的社交回复",
            }
        ],
    )
