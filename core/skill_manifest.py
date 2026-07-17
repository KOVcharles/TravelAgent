"""Backward-compatible imports for the pre-standard Skill API.

New code should import from :mod:`core.skill_definition`. The aliases remain so
older integrations do not fail immediately during the architecture migration.
"""
from core.skill_definition import (  # noqa: F401
    HommeySkillConfig,
    SkillDefinition,
    SkillDependency,
    SkillExecutionStep,
    SkillFrontmatter,
    load_skill_definition,
    parse_skill_md,
)

SkillManifest = SkillDefinition


def load_skill_manifest(path):
    """Load a definition from an old config path or a skill directory."""
    skill_dir = path.parent if path.name in {"manifest.yaml", "hommey.yaml"} else path
    return load_skill_definition(skill_dir)
