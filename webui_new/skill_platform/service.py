"""Application service for the administrator skill platform."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from core.skill_store import SkillPlatformStore
from utils.skill_loader import SkillLoader


class SkillPlatformService:
    def __init__(self, loader: Optional[SkillLoader] = None, store: Optional[SkillPlatformStore] = None):
        self.loader = loader or SkillLoader()
        self.store = store or SkillPlatformStore()

    def list_skills(self) -> List[Dict[str, Any]]:
        manifests = self.loader.load_manifests()
        settings = self.store.settings()
        runs = self.store.recent_runs(limit=500)
        metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"total": 0, "success": 0, "duration": 0})
        for run in runs:
            metric = metrics[run["skill_name"]]
            metric["total"] += 1
            metric["success"] += int(run["status"] == "success")
            metric["duration"] += int(run.get("duration_ms") or 0)

        result = []
        for manifest in sorted(manifests.values(), key=lambda item: (item.catalog_order, item.name)):
            setting = settings.get(manifest.name, {})
            metric = metrics[manifest.name]
            total = metric["total"]
            result.append({
                **manifest.model_dump(),
                "enabled": setting.get("enabled", manifest.enabled_by_default),
                "metrics": {
                    "runs": total,
                    "success_rate": round(metric["success"] / total, 4) if total else None,
                    "average_duration_ms": round(metric["duration"] / total) if total else None,
                },
            })
        return result

    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        skill = next((item for item in self.list_skills() if item["name"] == skill_name), None)
        if not skill:
            return None
        skill["instructions"] = self.loader.get_skill_content(skill_name) or ""
        skill["recent_runs"] = self.store.recent_runs(limit=20, skill_name=skill_name)
        return skill

    def dependency_graph(self) -> Dict[str, Any]:
        manifests = self.loader.load_manifests()
        nodes = [
            {"id": item.name, "label": item.display_name, "category": item.category}
            for item in manifests.values()
        ]
        edges = []
        for item in manifests.values():
            for dependency in item.requires:
                edges.append({"source": dependency.skill, "target": item.name, "purpose": dependency.purpose})
        return {"nodes": nodes, "edges": edges}
