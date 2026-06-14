import json
import asyncio

from agents.orchestration_agent import OrchestrationAgent
from agentscope.message import Msg


def test_orchestration_returns_no_agents_for_empty_schedule():
    orchestrator = OrchestrationAgent(agent_registry={}, memory_manager=None)

    result = asyncio.run(
        orchestrator.reply(
            Msg(
                name="intention",
                content=json.dumps({"agent_schedule": []}),
                role="assistant",
            )
        )
    )

    payload = json.loads(result.content)
    assert payload["status"] == "no_agents"


def test_orchestration_rejects_invalid_intention_json():
    orchestrator = OrchestrationAgent(agent_registry={}, memory_manager=None)

    result = asyncio.run(
        orchestrator.reply(
            Msg(name="intention", content="not-json", role="assistant")
        )
    )

    payload = json.loads(result.content)
    assert payload["error"] == "Invalid intention format"
