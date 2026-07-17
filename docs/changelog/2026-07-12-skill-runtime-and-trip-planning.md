# Skill 运行时与行程规划优化

> 架构说明：本文记录 2026-07-12 当时的 Manifest 方案。当前 Skill 已迁移为标准 `SKILL.md` frontmatter + 可选 `hommey.yaml` 扩展，参见 [2026-07-17 标准 Agent Skill 架构迁移](2026-07-17-standard-agent-skill-architecture.md)。

## 背景

本次调整聚焦两个问题：

1. Skill 的机器元数据曾同时存在于 `SKILL.md` front matter 与 `manifest.yaml`，容易发生漂移。
2. 企业出差规划在多轮收集、RAG、公开信息查询、行程输出和最终呈现之间存在编排与契约问题，导致普通规划请求可能只显示中间结果或“已完成”兜底文案。

## Skill 元数据边界

`manifest.yaml` 现在是唯一机器可读元数据来源，负责声明：

- 名称、版本、分类与意图；
- Agent 名称与执行入口；
- 工具、风险、依赖和执行优先级；
- 输入输出 Schema 与默认启停状态。

`SKILL.md` 不再保存 YAML front matter，只保存具体方法、流程与模型约束。

`SkillLoader` 只通过 Manifest 发现 Skill，并验证每个 Manifest 都有配套的 `SKILL.md` 流程文件。

## 流式模型输出修复

部分 OpenAI 兼容模型会在流式调用中重复返回“截至当前的完整文本”，而非只返回新增 token。旧实现直接拼接每个 chunk，会将 JSON 破坏为重复片段，导致意图识别解析失败。

公共文本提取器现在同时兼容：

- 增量 chunk：追加新文本；
- 累计全文 chunk：使用最新全文覆盖已有文本。

这避免了正常的意图 JSON 被解析为 `unclear`，从而返回“无法可靠理解”的兜底回复。

## 多 Agent 聚合修复

`OrchestrationAgent._aggregate_results()` 现在明确返回聚合结果。

此前该函数缺少 `return aggregated`，多 Agent 执行后会被序列化为 JSON `null`，Web 层再调用 `.get()` 时会失败。修复后协调器可正常返回各 Agent 的结构化结果。

## 行程规划工作流

`plan-trip` 的声明式执行顺序更新为：

```text
Priority 1  event-collection
Priority 2  ask-question + query-info（并行）
Priority 3  itinerary-planning
Priority 4  trip-compliance
```

### 事项完整性门槛

行程规划的必填字段为：

- 出发地；
- 目的地；
- 出发日期；
- 出差目的；
- 出差天数或返程日期。

工作地点与会面/工作时间为可选字段，只用于优化安排，不阻塞规划。

`event-collection` 负责用模型从用户当轮输入、用户偏好和当前出差任务中提取信息；随后代码根据上述字段确定性计算 `planning_ready`。这意味着完整性判断并不只依赖模型的 `missing_info`。

若事项不完整，协调器在事项收集后停止，不会调用 RAG、天气/交通查询、行程规划或合规检查。

### 多轮上下文与自动续跑

事项收集结果会通过 `MemoryManager.update_active_trip()` 增量写入每个用户的当前出差任务。

下一轮输入时，当前任务会作为 `active_trip` 注入意图识别和事项收集上下文。新字段与原任务合并，已有目的地、日期等信息不会被空值覆盖。

当本轮补齐最后一个必填字段时，协调器会自动追加并运行剩余工作流：

```text
ask-question + query-info → itinerary-planning → trip-compliance
```

用户不需要再额外输入“生成”。

### 制度与公开信息分工

`ask-question` 在规划工作流中会依据已收集的行程生成制度导向的子查询，例如住宿、交通、补贴、报销和审批规则；它不再把“北京到南昌怎么走”作为 RAG 查询。

`query-info` 会根据完整的出发地、目的地和日期并行获取：

- 目的地天气；
- 路线级公开交通信息。

公开信息仅作为建议，必须提醒用户通过铁路、航司或授权差旅渠道核验实时车次、航班、票价和可订状态。外部查询不可用时，行程 Agent 仍可提供路线级建议。

### 规划输出契约兼容

页面渲染使用以下契约：

```json
{
  "itinerary": {
    "daily_plans": []
  },
  "planning_complete": true
}
```

部分模型会返回旧式 `trip.daily_schedule`。行程执行器现在会把这类结果规范化为 `itinerary.daily_plans`，并强制 Prompt 直接输出标准契约，避免已生成行程却只显示“规划已完成”的情况。

## 最终呈现

当行程已生成时，Web 页面隐藏以下中间结果：

- 事项收集原始结果；
- RAG 原始回答；
- 天气与公开交通的原始查询摘要。

这些信息仍会传给行程 Agent，最终由行程回答整合展示。

事项未完整时，页面以用户可读标签展示必要与可选信息，例如：

```text
为开始生成行程，请补充：出发日期（如：7月14日）；出差目的（如：拜访客户、参加会议）
可选补充（有助于优化安排）：客户/会议地点；会面或工作时间
```

当没有足以形成确定结论的制度证据时，不再单独展示大段“合规未知”卡片；行程末尾仅提示用户在提交前人工确认。

## 验证与运行

本次变更包含 Skill Manifest、路由优先级、事项门槛、自动续跑、输出规范化和页面呈现的回归测试。

应用使用开发 Compose 配置运行，代码验证后通过以下命令重启应用容器加载：

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml restart hommey
```

数据库与 Redis 无需重启。
