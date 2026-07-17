# 标准 Agent Skill 架构迁移

## 目标

运行时 Skill 改为兼容通用 Agent Skills 的包结构，同时保留 Hommey 的企业治理、Agent 执行器和声明式工作流能力。

## 新结构

```text
.claude/skills/<skill-name>/
├── SKILL.md       # 标准 name/description frontmatter + 指令正文
├── hommey.yaml    # 可选 Hommey 运行时扩展
├── script/
├── schemas/
├── references/
└── agents/
```

`SKILL.md` 现在是能力发现的唯一来源。`hommey.yaml` 不再重复 `name` 和 `description`，只保存版本、展示名、意图、执行器、工具、风险、依赖和执行计划。只有 `SKILL.md` 的标准 Skill 也可以被 `SkillLoader` 发现，但不会进入 Hommey 意图目录、Agent 注册表、管理页或调度计划。

## 运行时变化

- `core/skill_definition.py` 分别校验 frontmatter 和 Hommey 扩展，并合并为 `SkillDefinition`。
- `SkillLoader.load_definitions()` 是新的内部 API；旧的 `load_manifests()` 暂时作为兼容别名保留。
- `SkillLoader.get_skill_content()` 会剥离 frontmatter，只把 Markdown 指令正文交给 Agent。
- 意图目录、懒加载注册表、协调器和管理平台统一消费 `SkillDefinition`。
- 原有 `manifest.yaml` 已迁移为 `hommey.yaml`。

## 兼容性

标准 Agent Skills 客户端可以直接根据 `SKILL.md` 发现这些 Skill，并忽略 `hommey.yaml`。Hommey 仍使用扩展文件提供原有 AgentScope 执行、启停、依赖图、风险和执行轨迹能力。
