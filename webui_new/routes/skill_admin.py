"""Administrator-only Skill platform API."""
from fastapi import APIRouter, Depends

from webui_new.auth import User, require_admin
from webui_new.core.errors import BusinessError
from webui_new.schemas.requests import SkillToggleRequest


def create_skill_admin_router(service):
    router = APIRouter(prefix="/api/admin/skills", tags=["skill-admin"])

    @router.get("")
    async def list_skills(current_user: User = Depends(require_admin)):
        return {
            "skills": service.list_skills(),
            "graph": service.dependency_graph(),
            "runs": service.store.recent_runs(limit=100),
        }

    @router.get("/{skill_name}")
    async def get_skill(skill_name: str, current_user: User = Depends(require_admin)):
        skill = service.get_skill(skill_name)
        if not skill:
            raise BusinessError("SKILL_NOT_FOUND", "Skill 不存在", status_code=404)
        return skill

    @router.patch("/{skill_name}/enabled")
    async def toggle_skill(
        skill_name: str,
        data: SkillToggleRequest,
        current_user: User = Depends(require_admin),
    ):
        definition = service.loader.get_definition(skill_name)
        if not definition:
            raise BusinessError("SKILL_NOT_FOUND", "Skill 不存在", status_code=404)
        if not service.store.configured:
            raise BusinessError("SKILL_STORE_UNAVAILABLE", "Skill 配置存储尚未启用", status_code=503)
        service.store.set_enabled(skill_name, data.enabled, str(current_user.id))
        return {"skill_name": skill_name, "enabled": data.enabled}

    return router
