import asyncio
import json
from pathlib import Path

import pytest
from agents.lazy_agent_registry import LazyAgentRegistry
from agents.orchestration_agent import OrchestrationAgent
from agentscope.message import Msg

from context.long_term_memory import FileLongTermMemory
from core.schedule_builder import build_agent_schedule
from utils.skill_loader import SkillLoader
from webui_new.auth.deps import require_admin
from webui_new.auth.storage import User
from webui_new.core.errors import BusinessError
from webui_new.skill_platform import SkillPlatformService
from webui_new.routes.skill_admin import create_skill_admin_router


class _Store:
    configured = True

    def __init__(self):
        self.values = {}

    def settings(self):
        return self.values

    def recent_runs(self, limit=100, skill_name=None):
        return []

    def set_enabled(self, skill_name, enabled, updated_by):
        self.values[skill_name] = {"enabled": enabled, "updated_by": updated_by}


class _DisabledStore(_Store):
    configured = False

    def is_enabled(self, skill_name, default=True):
        return skill_name != "ask-question"


def test_every_skill_has_a_valid_manifest_and_known_tools():
    loader = SkillLoader()
    skills = loader.load_skills()
    manifests = loader.load_manifests()

    assert set(skills) == set(manifests)
    assert manifests["plan-trip"].category == "workflow"
    assert manifests["check-trip-compliance"].risk_level == "high"
    assert "rag_retrieval" in manifests["check-trip-compliance"].tools


def test_plan_workflow_is_declarative_and_ends_with_compliance():
    schedule = build_agent_schedule([{"type": "itinerary_planning"}])

    assert [(item["agent_name"], item["priority"]) for item in schedule] == [
        ("event_collection", 1),
        ("rag_knowledge", 1),
        ("itinerary_planning", 2),
        ("trip_compliance", 3),
    ]


def test_disabled_skill_is_removed_before_orchestration():
    orchestrator = OrchestrationAgent(agent_registry={}, skill_store=_DisabledStore())

    filtered, disabled = orchestrator._filter_enabled_schedule(
        [
            {"agent_name": "rag_knowledge", "priority": 1},
            {"agent_name": "itinerary_planning", "priority": 2},
        ]
    )

    assert filtered == [{"agent_name": "itinerary_planning", "priority": 2}]
    assert disabled == ["ask-question"]


def test_compliance_skill_refuses_a_definite_verdict_without_rag_evidence():
    registry = LazyAgentRegistry(model=None, cache={})
    agent = registry["trip_compliance"]
    response = asyncio.run(
        agent.reply(
            Msg(
                name="Orchestrator",
                content=json.dumps(
                    {
                        "context": {"active_trip": {"destination": "南京"}},
                        "previous_results": [
                            {
                                "agent_name": "event_collection",
                                "result": {"data": {"origin": "上海", "destination": "南京"}},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                role="user",
            )
        )
    )
    data = json.loads(response.content)

    assert data["status"] == "insufficient_evidence"
    assert data["verdict"] == "unknown"
    assert data["sources"] == []


def test_file_memory_keeps_one_incrementally_updated_active_trip(tmp_path):
    memory = FileLongTermMemory("u1", storage_path=str(tmp_path))

    memory.upsert_active_trip({"destination": "南京", "missing_info": ["出发地"]})
    updated = memory.upsert_active_trip({"origin": "上海", "missing_info": []})

    assert updated["destination"] == "南京"
    assert updated["origin"] == "上海"
    assert memory.get_active_trip()["missing_info"] == []


def test_skill_platform_service_exposes_dependency_graph():
    service = SkillPlatformService(store=_Store())

    skills = service.list_skills()
    graph = service.dependency_graph()

    assert any(item["name"] == "check-trip-compliance" for item in skills)
    assert any(
        edge["source"] == "check-trip-compliance" and edge["target"] == "plan-trip"
        for edge in graph["edges"]
    )


def test_require_admin_rejects_normal_user_and_accepts_admin():
    normal = User(1, "user@example.com", "hash", "now", role="user")
    admin = User(2, "admin@example.com", "hash", "now", role="admin")

    with pytest.raises(BusinessError) as exc:
        asyncio.run(require_admin(normal))
    assert exc.value.status_code == 403
    assert asyncio.run(require_admin(admin)) == admin


def test_skill_platform_migration_is_non_destructive():
    sql = Path("webui_new/auth/migrations/0002_skill_platform.sql").read_text(encoding="utf-8")

    assert "active_trip_contexts" in sql
    assert "skill_settings" in sql
    assert "skill_execution_runs" in sql
    assert "DROP TABLE" not in sql.upper()


def test_admin_skill_api_registers_management_routes():
    store = _Store()
    service = SkillPlatformService(store=store)
    router = create_skill_admin_router(service)

    paths = {(route.path, tuple(sorted(route.methods))) for route in router.routes}
    assert ("/api/admin/skills", ("GET",)) in paths
    assert ("/api/admin/skills/{skill_name}", ("GET",)) in paths
    assert ("/api/admin/skills/{skill_name}/enabled", ("PATCH",)) in paths
