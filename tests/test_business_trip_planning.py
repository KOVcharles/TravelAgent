import asyncio
import json

from agents.lazy_agent_registry import LazyAgentRegistry
from agentscope.message import Msg
from utils.skill_loader import SkillLoader
from webui_new.manager import HommeyWebInstance


def test_plan_trip_skill_is_business_focused_and_advice_only():
    content = SkillLoader().get_skill_content("plan-trip")

    assert "公司差旅" in content
    assert "不得编造真实车次" in content
    assert "不执行预订、付款、审批" in content
    assert "reimbursement_checklist" in content
    assert "必须给出具体的景点" not in content


def test_itinerary_agent_receives_business_trip_constraints():
    prompts = []
    payload = {
        "itinerary": {
            "title": "南京公司差旅方案",
            "duration": "2天",
            "transport_recommendation": {
                "preferred": "高铁",
                "reason": "耗时稳定",
                "verification": "请以铁路官方渠道为准",
            },
            "daily_plans": [],
            "reimbursement_checklist": ["交通票据", "住宿发票"],
            "missing_info": ["出发日期"],
        },
        "planning_complete": False,
    }

    async def fake_model(messages):
        prompts.append(messages[0]["content"])
        return json.dumps(payload, ensure_ascii=False)

    registry = LazyAgentRegistry(model=fake_model, cache={})
    agent = registry["itinerary_planning"]
    response = asyncio.run(
        agent.reply(
            Msg(
                name="Orchestrator",
                content=json.dumps(
                    {"context": {"rewritten_query": "帮我规划去南京出差的路线"}},
                    ensure_ascii=False,
                ),
                role="user",
            )
        )
    )
    data = json.loads(response.content)

    assert data["itinerary"]["transport_recommendation"]["preferred"] == "高铁"
    assert "不得编造真实车次" in prompts[0]
    assert "仅提供建议" in prompts[0]


def test_web_formatter_displays_transport_and_reimbursement_advice():
    instance = object.__new__(HommeyWebInstance)
    text = instance._format_agent_result(
        "itinerary_planning",
        {
            "itinerary": {
                "title": "南京公司差旅方案",
                "duration": "2天",
                "transport_recommendation": {
                    "preferred": "高铁",
                    "reason": "耗时稳定",
                    "verification": "最终核验车次和余票",
                },
                "lodging_advice": "住在会议地点附近",
                "daily_plans": [],
                "reimbursement_checklist": ["交通票据", "住宿发票"],
                "estimated_budget": "待确认公司标准后估算",
                "missing_info": ["出发地"],
            }
        },
    )

    assert "首选: 高铁" in text
    assert "住宿建议" in text
    assert "报销准备" in text
    assert "交通票据" in text
    assert "待补充" in text
