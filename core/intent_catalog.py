"""意图 ↔ Skill 单一目录（single source of truth）。

每个 skill-backed 意图 1:1 对应一个 skill 目录；非 skill 意图（unclear / unsupported）
不调用任何 skill，由主流程直接处理。

消费方：
- agents/intention_agent.py —— 用 build_intent_prompt_section() 渲染 prompt 的意图列表，
  用 intent_to_skill() 替代本地 skill_mapping。
- core/intent_guard.py / core/intent_router.py —— 用 CHITCHAT_EXACT / CHITCHAT_KEYWORDS
  识别寒暄，并统一路由到 chitchat skill。
- cli.py / webui.py / webui_new/manager.py —— 用 INTENT_DISPLAY_NAMES 统一中文标签。

一致性由 tests/test_intent_catalog.py 保证：目录中的 skill 集合必须与
utils.skill_loader 实际发现的 skill 目录一致，防止漂移。
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional, Tuple

# skill-backed 意图：intent_name -> 元信息
# 顺序即 prompt 中展示的顺序；description 为面向意图分类的简洁中文说明。
SKILL_INTENTS: Dict[str, Dict[str, str]] = {
    "chitchat": {
        "skill": "chitchat",
        "description": "寒暄、感谢、告别、闲聊、情绪表达等社交对话",
        "display": "闲聊",
    },
    "preference": {
        "skill": "preference",
        "description": "用户表达或更新个人偏好（酒店、航司、座位、常驻地等）",
        "display": "偏好管理",
    },
    "memory_query": {
        "skill": "memory-query",
        "description": "查询用户自己的历史、偏好、过去行程",
        "display": "记忆查询",
    },
    "event_collection": {
        "skill": "event-collection",
        "description": "收集行程基础信息（出发地、目的地、日期、目的等）",
        "display": "事项收集",
    },
    "itinerary_planning": {
        "skill": "plan-trip",
        "description": "规划未来行程，通常依赖 event_collection 的结果",
        "display": "行程规划",
    },
    "information_query": {
        "skill": "query-info",
        "description": "天气、实时信息、普通联网搜索",
        "display": "信息查询",
    },
    "rag_knowledge": {
        "skill": "ask-question",
        "description": "差旅标准、报销、政策、制度问答（企业知识库）",
        "display": "知识库查询",
    },
    "mcp_tool": {
        "skill": "mcp-tool",
        "description": "需要外部 MCP 工具操作（文件读写、系统操作等）",
        "display": "MCP 工具",
    },
}

# 非 skill 意图：不调用任何 skill，由主流程直接处理
NON_SKILL_INTENTS: Dict[str, Dict[str, str]] = {
    "unclear": {
        "description": "输入太短、模糊、半句话或无法确定意图，不调用 skill",
        "display": "需澄清",
    },
    "unsupported": {
        "description": "当前系统不支持的请求（如付款、转账、删库等），不调用 skill",
        "display": "不支持",
    },
}


def all_intents() -> Dict[str, Dict[str, str]]:
    """全部意图（skill-backed + 非 skill）。"""
    return {**SKILL_INTENTS, **NON_SKILL_INTENTS}


# 反查：skill 目录名 -> intent_name
_SKILL_TO_INTENT: Dict[str, str] = {
    info["skill"]: intent for intent, info in SKILL_INTENTS.items()
}


def intent_to_skill(intent: str) -> Optional[str]:
    """意图名 -> skill 目录名；非 skill 意图或未知意图返回 None。"""
    info = SKILL_INTENTS.get(intent)
    return info["skill"] if info else None


def skill_to_intent(skill: str) -> Optional[str]:
    """skill 目录名 -> 意图名；未知 skill 返回 None。"""
    return _SKILL_TO_INTENT.get(skill)


def is_skill_intent(intent: str) -> bool:
    return intent in SKILL_INTENTS


# 统一中文显示名（含非 skill 意图）
INTENT_DISPLAY_NAMES: Dict[str, str] = {
    intent: info["display"] for intent, info in all_intents().items()
}


def display_name(intent: str) -> str:
    """意图 -> 中文显示名；未知意图原样返回。"""
    return INTENT_DISPLAY_NAMES.get(intent, intent)


# 寒暄关键词（guard / router 共用，消除原先分散在多个模块的重叠关键词集）
# 短问候的精确匹配集 —— 必须在 guard 的 length<=2 判断之前命中，
# 否则"你好/在吗/嗨"等 1~2 字输入会被误判为 unclear。
CHITCHAT_EXACT: FrozenSet[str] = frozenset({
    "你好", "您好", "嗨", "哈喽",
    "hi", "hello", "hey",
    "在吗", "在不在", "有人吗",
    "谢谢", "感谢", "多谢",
    "再见", "拜拜", "bye",
    "ok", "okay", "好的",
})

# 寒暄的子串关键词（较长输入的包含匹配）
CHITCHAT_KEYWORDS: Tuple[str, ...] = (
    "你好", "您好", "嗨", "哈喽", "在吗",
    "你是什么", "你是谁", "你叫什么", "你能做什么", "你会什么", "介绍一下",
    "谢谢", "感谢", "再见",
)


def build_intent_prompt_section() -> str:
    """渲染 prompt 中的【意图类型】列表（skill-backed + 非 skill）。"""
    lines = []
    for intent, info in SKILL_INTENTS.items():
        lines.append(f"- {intent}: {info['description']}")
    for intent, info in NON_SKILL_INTENTS.items():
        lines.append(
            f"- {intent}: {info['description']}（不调用 skill，agent_schedule 必须为空）"
        )
    return "\n".join(lines)
