#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lazy plugin registry for skill-backed agents.

The runtime skill root is controlled by config.SKILL_CONFIG["root"] or the
ALIGO_SKILLS_ROOT environment variable. It defaults to .claude/skills for
backward compatibility with the current repository layout.
"""
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from agentscope.agent import AgentBase
from rich.console import Console

from config import SKILL_CONFIG


class LazyAgentRegistry:
    """Discover skill plugins and instantiate their AgentBase subclasses on use."""

    _legacy_mapping = {
        "rag_knowledge": "ask-question",
        "memory_query": "memory-query",
        "preference": "preference",
        "information_query": "query-info",
        "itinerary_planning": "plan-trip",
        "event_collection": "event-collection",
        "chitchat": "chitchat",
        "mcp_tool": "mcp-tool",
    }

    def __init__(
        self,
        model,
        cache: Dict,
        memory_manager=None,
        mcp_manager=None,
        skills_root: Optional[str] = None,
    ):
        self.model = model
        self.cache = cache
        self.memory_manager = memory_manager
        self.mcp_manager = mcp_manager
        self.console = Console()

        project_root = Path(__file__).parent.parent.resolve()
        configured_root = skills_root or SKILL_CONFIG.get("root", ".claude/skills")
        self.skills_root = Path(configured_root)
        if not self.skills_root.is_absolute():
            self.skills_root = project_root / self.skills_root
        self.skills_root = self.skills_root.resolve()

        self._skill_map: Dict[str, Path] = {}
        self._discover_skills()

    def _discover_skills(self) -> None:
        if not self.skills_root.exists():
            self.console.print(
                f"[yellow]Warning: Skills directory {self.skills_root} not found[/yellow]"
            )
            return

        for skill_dir in sorted(self.skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue

            agent_script = skill_dir / "script" / "agent.py"
            if agent_script.exists():
                self._skill_map[skill_dir.name] = agent_script

    def _resolve_agent_name(self, agent_name: str) -> Optional[str]:
        if agent_name in self._skill_map:
            return agent_name

        skill_name = self._legacy_mapping.get(agent_name)
        if skill_name and skill_name in self._skill_map:
            return skill_name

        return None

    def __getitem__(self, agent_name: str):
        if agent_name in self.cache:
            return self.cache[agent_name]

        skill_name = self._resolve_agent_name(agent_name)
        if not skill_name:
            available = ", ".join(self.keys()) or "none"
            raise KeyError(
                f"Agent '{agent_name}' not found under {self.skills_root}. "
                f"Available agents: {available}"
            )

        script_path = self._skill_map[skill_name]
        self.console.print(f"[dim]Loading {agent_name} from skill {skill_name}...[/dim]")

        try:
            safe_skill_name = skill_name.replace("-", "_")
            module_name = f"aligo_dynamic_skills.{safe_skill_name}.agent"
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load spec from {script_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            project_root = str(Path(__file__).parent.parent.resolve())
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            spec.loader.exec_module(module)

            agent_class = None
            for _, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, AgentBase) and obj is not AgentBase:
                    agent_class = obj
                    break

            if not agent_class:
                raise ValueError(f"No AgentBase subclass found in {script_path}")

            init_params = {
                "name": agent_name,
                "model": self.model,
            }

            sig = inspect.signature(agent_class.__init__)
            if "memory_manager" in sig.parameters:
                init_params["memory_manager"] = self.memory_manager
            if "mcp_manager" in sig.parameters:
                init_params["mcp_manager"] = self.mcp_manager

            agent_instance = agent_class(**init_params)
            self.cache[agent_name] = agent_instance
            self.console.print(f"[dim]{agent_name} loaded[/dim]")
            return agent_instance
        except Exception as exc:
            self.console.print(f"[red]Failed to load {agent_name}: {exc}[/red]")
            raise

    def __contains__(self, agent_name: str) -> bool:
        return self._resolve_agent_name(agent_name) is not None or agent_name in self.cache

    def get(self, agent_name: str, default=None):
        try:
            return self[agent_name]
        except KeyError:
            return default

    def keys(self):
        keys = set(self._skill_map.keys())
        for legacy_key, skill_name in self._legacy_mapping.items():
            if skill_name in self._skill_map:
                keys.add(legacy_key)
        return sorted(keys)

    def values(self):
        return self.cache.values()

    def items(self):
        return self.cache.items()

    def get_loaded_agents(self) -> list:
        return list(self.cache.keys())
