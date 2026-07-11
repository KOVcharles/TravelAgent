"""Validated runtime contract for TravelAgent skills."""
from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    required: bool = True
    purpose: str = ""


class SkillExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    agent_name: str
    priority: int = Field(ge=1)
    reason: str = ""
    expected_output: str = ""


class SkillManifest(BaseModel):
    """Machine-readable metadata kept separate from concise SKILL.md instructions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    display_name: str
    description: str
    category: Literal["business", "workflow", "capability", "interaction"]
    domain: str = "business-travel"
    intent: Optional[str] = None
    agent_name: Optional[str] = None
    entrypoint: str = "script/agent.py"
    user_facing: bool = True
    enabled_by_default: bool = True
    risk_level: Literal["low", "medium", "high"] = "low"
    catalog_order: int = 100
    tools: List[Literal[
        "active_trip_context", "rag_retrieval", "travel_information",
        "weather", "web_search", "memory", "mcp",
    ]] = Field(default_factory=list)
    requires: List[SkillDependency] = Field(default_factory=list)
    execution: List[SkillExecutionStep] = Field(default_factory=list)
    input_schema: Optional[str] = None
    output_schema: Optional[str] = None

    @model_validator(mode="after")
    def validate_runtime_contract(self):
        if self.intent and not self.agent_name:
            raise ValueError("intent-backed skills require agent_name")
        if self.intent and not self.execution:
            raise ValueError("intent-backed skills require an execution plan")
        return self

    def validate_resources(self, skill_dir: Path) -> None:
        entrypoint = skill_dir / self.entrypoint
        if self.agent_name and not entrypoint.exists():
            raise ValueError(f"Missing skill entrypoint: {entrypoint}")
        for relative in (self.input_schema, self.output_schema):
            if relative and not (skill_dir / relative).exists():
                raise ValueError(f"Missing skill schema: {skill_dir / relative}")


def load_skill_manifest(path: Path) -> SkillManifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Skill manifest must be a mapping: {path}")
    manifest = SkillManifest.model_validate(data)
    if manifest.name != path.parent.name:
        raise ValueError(
            f"Skill manifest name '{manifest.name}' must match directory '{path.parent.name}'"
        )
    manifest.validate_resources(path.parent)
    return manifest
