import asyncio
import json

from agents.intention_agent import IntentionAgent
from agents.orchestration_agent import OrchestrationAgent
from agentscope.message import Msg
from core.intent_guard import can_call_information_query, guard_user_input
from core.intent_router import FastIntentRouter


def _schedule_agents(route):
    data = route.to_intention_data("")
    return [item.get("agent_name") for item in data.get("agent_schedule", [])]


def test_short_input_does_not_call_information_query():
    result = guard_user_input("你?")

    assert result is not None
    assert result.intent == "unclear"
    assert result.should_call_skill is False
    assert result.agent_schedule == []


def test_chitchat_routes_to_skill():
    route = FastIntentRouter.route("在吗")

    assert route is not None
    data = route.to_intention_data("在吗")
    assert data["routing"]["intent"] == "chitchat"
    assert data["routing"]["should_call_skill"] is True
    assert _schedule_agents(route) == ["chitchat"]


def test_clear_weather_query_routes_to_information_query():
    route = FastIntentRouter.route("帮我查一下明天东京天气")

    assert route is not None
    data = route.to_intention_data("帮我查一下明天东京天气")
    assert data["routing"]["intent"] == "information_query"
    assert data["routing"]["should_call_skill"] is True
    assert _schedule_agents(route) == ["information_query"]


def test_trip_request_routes_to_trip_planning():
    route = FastIntentRouter.route("我下周去上海出差，帮我安排两天行程")

    assert route is not None
    data = route.to_intention_data("我下周去上海出差，帮我安排两天行程")
    assert data["routing"]["intent"] == "itinerary_planning"
    assert _schedule_agents(route) == ["event_collection", "itinerary_planning"]


def test_policy_query_routes_to_rag_knowledge():
    route = FastIntentRouter.route("餐补标准是多少")

    assert route is not None
    data = route.to_intention_data("餐补标准是多少")
    assert data["routing"]["intent"] == "rag_knowledge"
    assert _schedule_agents(route) == ["rag_knowledge"]


def test_vague_browse_input_is_unclear_without_skill():
    result = guard_user_input("随便看看")

    assert result is not None
    assert result.intent == "unclear"
    assert result.should_call_skill is False
    assert result.agent_schedule == []


def test_information_query_requires_clear_target():
    result = can_call_information_query("查一下", 0.9)

    assert result.intent == "unclear"
    assert result.should_call_skill is False
    assert result.agent_schedule == []


def test_intention_connection_error_falls_back_without_information_query():
    async def failing_model(_messages):
        raise RuntimeError("Connection error")

    agent = IntentionAgent(name="IntentionAgent", model=failing_model)
    result = asyncio.run(agent.reply(Msg(name="user", content="帮我处理一下这个事情", role="user")))
    data = json.loads(result.content)

    assert data["routing"]["intent"] == "fallback"
    assert data["routing"]["should_call_skill"] is False
    assert data["agent_schedule"] == []


def test_low_confidence_skill_call_is_blocked():
    async def low_confidence_model(_messages):
        return json.dumps(
            {
                "reasoning": "low confidence",
                "routing": {
                    "intent": "rag_knowledge",
                    "confidence": 0.4,
                    "reason": "not sure",
                    "should_call_skill": True,
                },
                "intents": [
                    {
                        "type": "rag_knowledge",
                        "confidence": 0.4,
                        "description": "",
                        "reason": "not sure",
                        "should_call_skill": True,
                    }
                ],
                "key_entities": {},
                "rewritten_query": "帮我处理这个内容",
                "agent_schedule": [
                    {
                        "agent_name": "rag_knowledge",
                        "priority": 1,
                        "reason": "not sure",
                        "expected_output": "",
                    }
                ],
            },
            ensure_ascii=False,
        )

    agent = IntentionAgent(name="IntentionAgent", model=low_confidence_model)
    result = asyncio.run(agent.reply(Msg(name="user", content="帮我处理这个内容", role="user")))
    data = json.loads(result.content)

    assert data["routing"]["should_call_skill"] is False
    assert data["intents"][0]["should_call_skill"] is False
    assert data["agent_schedule"] == []


def test_orchestrator_respects_should_not_call_skill():
    orchestrator = OrchestrationAgent(agent_registry={"information_query": object()}, memory_manager=None)
    payload = {
        "routing": {
            "intent": "unclear",
            "confidence": 0.9,
            "reason": "输入过短",
            "should_call_skill": False,
        },
        "agent_schedule": [{"agent_name": "information_query", "priority": 1}],
    }

    result = asyncio.run(
        orchestrator.reply(
            Msg(name="intention", content=json.dumps(payload, ensure_ascii=False), role="assistant")
        )
    )
    data = json.loads(result.content)

    assert data["status"] == "no_agents"
    assert data["results"] == []
