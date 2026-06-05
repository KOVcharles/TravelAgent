from pathlib import Path
from typing import Dict, Optional

import yaml

from config import SKILL_CONFIG


class SkillLoader:
    """Load SKILL.md metadata and prompt content from the configured skill root."""

    def __init__(self, skills_dir: Optional[str] = None):
        project_root = Path(__file__).parent.parent.resolve()
        configured_dir = skills_dir or SKILL_CONFIG.get("root", ".claude/skills")
        self.skills_dir = Path(configured_dir)
        if not self.skills_dir.is_absolute():
            self.skills_dir = project_root / self.skills_dir
        self.skills_dir = self.skills_dir.resolve()
        self.skills: Dict[str, Dict] = {}

    def load_skills(self) -> Dict[str, Dict]:
        if not self.skills_dir.exists():
            print(f"Warning: Skills directory {self.skills_dir} not found.")
            return {}

        self.skills = {}
        for skill_path in sorted(self.skills_dir.iterdir()):
            if not skill_path.is_dir():
                continue

            md_file = skill_path / "SKILL.md"
            if not md_file.exists():
                continue

            skill_info = self._parse_skill_md(md_file)
            if skill_info:
                skill_info.setdefault("directory", skill_path.name)
                self.skills[skill_info.get("name", skill_path.name)] = skill_info

        return self.skills

    def _parse_skill_md(self, file_path: Path) -> Optional[Dict]:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"Error reading {file_path}: {exc}")
            return None

        if not content.startswith("---"):
            return None

        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None

        yaml_content = content[3:end_idx]
        try:
            data = yaml.safe_load(yaml_content)
            return data if isinstance(data, dict) else None
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML in {file_path}: {exc}")
            return None

    def get_skill_prompt(self, skill_mapping: Optional[Dict[str, str]] = None) -> str:
        if not self.skills:
            self.load_skills()

        prompt_lines = []
        for index, (name, info) in enumerate(sorted(self.skills.items()), start=1):
            display_name = skill_mapping.get(name, name) if skill_mapping else name
            desc = info.get("description", "").replace("\n", " ")
            prompt_lines.append(f"{index}. {display_name} - {desc}")

        return "\n\n".join(prompt_lines)

    def get_skill_content(self, skill_name: str) -> Optional[str]:
        if not self.skills:
            self.load_skills()

        target_path = self.skills_dir / skill_name / "SKILL.md"
        if not target_path.exists():
            target_path = self._find_skill_by_metadata_name(skill_name)

        if not target_path:
            return None

        try:
            content = target_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"Error reading skill content {target_path}: {exc}")
            return None

        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx != -1:
                content = content[end_idx + 3 :].strip()
        return content

    def _find_skill_by_metadata_name(self, skill_name: str) -> Optional[Path]:
        if not self.skills_dir.exists():
            return None

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            md_path = skill_dir / "SKILL.md"
            if not md_path.exists():
                continue

            info = self._parse_skill_md(md_path)
            if info and info.get("name") == skill_name:
                return md_path

        return None
