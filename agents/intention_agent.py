"""
意图识别智能体 IntentionRecognitionAgent
职责：准确识别用户意图，并进行智能体调度

核心功能：
1. 多意图识别和分类：融合上下文对模糊意图进行消歧
2. 智能体调度决策：基于预定义的触发条件和业务规则，根据识别结果决定调用哪些子智能体
3. Query改写：标准化用户口语化的query输入，补全上下文信息，提取和重组关键信息
4. 显示推理：输出的两段式结构（推理过程 + JSON决策），提升意图识别准确度

架构：
- 使用单一LLM（用户配置的模型）
- 输入：用户query（自然语言）
- 输出：推理过程生成（包含reasoning+原因） + 多意图识别（原因） + 智能Query改写 + 构建结构化决策
"""
from agentscope.agent import AgentBase
from agentscope.message import Msg
from typing import Optional, Union, List
import json
import logging
from core.intent_catalog import build_intent_prompt_section
from core.intent_result import parse_json_object, validate_intent_result
from core.intent_router import FastIntentRouter
from core.intent_guard import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    INFORMATION_QUERY_THRESHOLD,
    can_call_information_query,
    guard_user_input,
    passes_confidence_gate,
)
from core.llm_response import extract_text_from_response

logger = logging.getLogger(__name__)


class IntentionAgent(AgentBase):
    """意图识别智能体（IntentionRecognitionAgent）"""

    def __init__(self, name: str = "IntentionRecognitionAgent", model=None, **kwargs):
        super().__init__()
        self.name = name
        self.model = model
        self.conversation_history = []

    async def reply(self, x: Optional[Union[Msg, List[Msg]]] = None) -> Msg:
        """
        意图识别主流程
        1. 推理过程生成
        2. 多意图识别
        3. 智能Query改写
        4. 构建结构化决策
        """
        if x is None:
            return Msg(name=self.name, content=json.dumps({}), role="assistant")

        # 获取用户查询
        if isinstance(x, list):
            user_query = x[-1].content if x else ""
            # 提取历史对话，保留角色信息
            self.conversation_history = []
            for msg in x[:-1]:
                if hasattr(msg, 'content') and hasattr(msg, 'role'):
                    # 区分处理不同角色的消息
                    if msg.role == "system":
                        # 长期记忆（system）- 完整保留，不截断
                        self.conversation_history.append(f"[系统记忆]\n{msg.content}")
                    else:
                        # 对话历史（user/assistant）- 适当截断但保留更多信息
                        role_name = "用户" if msg.role == "user" else "助手"
                        content = msg.content[:800] if len(msg.content) > 800 else msg.content
                        if len(msg.content) > 800:
                            content += "..."
                        self.conversation_history.append(f"{role_name}: {content}")
        else:
            user_query = x.content

        guard_result = guard_user_input(user_query)
        if guard_result:
            result = guard_result.to_intention_data(user_query)
            return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

        fast_route = FastIntentRouter.route(user_query)
        if fast_route:
            result = fast_route.to_intention_data(user_query)
            return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

        # 构建上下文
        # 策略：长期记忆始终保留，短期对话全部保留（已在 cli.py 控制数量）
        context_parts = []
        system_memory = None
        dialogue_history = []

        for item in self.conversation_history:
            if item.startswith("[系统记忆]"):
                system_memory = item  # 保存长期记忆
            else:
                dialogue_history.append(item)  # 保存对话历史

        # 组装上下文：长期记忆 + 全部对话
        if system_memory:
            context_parts.append(system_memory)
        if dialogue_history:
            context_parts.extend(dialogue_history) 

        context_str = "\n".join(context_parts) if context_parts else "无历史对话"

        # 获取当前时间
        from datetime import datetime
        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][datetime.now().weekday()]

        # 意图目录（单一来源：core/intent_catalog.py，intent ↔ skill 1:1）
        intent_list = build_intent_prompt_section()

        # 构建意图识别Prompt（合并版：精简路由 + guardrail + 消歧/改写/优先级语义）
        prompt = f"""你是一个高级意图识别专家（IntentionRecognitionAgent）。请分析用户查询，识别意图并输出结构化的调度决策。只输出 JSON，不要输出任何解释或 markdown 代码块。

【当前时间】
{current_time} {weekday}
（重要：当用户说"明天"、"后天"、"下周一"、"2月28日"等相对或无年份日期时，请根据当前时间推断为完整日期，填入 key_entities.date。）

【用户Query】
{user_query}

【对话历史上下文】
{context_str}

【意图类型（intent ↔ skill 1:1，agent_schedule 的 agent_name 用意图名）】
{intent_list}

【意图区分原则 - 基于语义而非关键词】
同一个词在不同语境下对应不同意图：
- "我去过北京吗？" → memory_query（询问自己的历史）
- "北京怎么样？" / "北京有什么好玩的？" → information_query（询问客观信息）
- "我想去北京" → itinerary_planning（规划未来行程）
- "差旅住宿标准是多少" → rag_knowledge（企业制度/政策）
当问题涉及"我的/我之前/我去过"等用户自身历史时，必须优先 memory_query，优先级高于 information_query。

【调度规则】
- 简单单意图只调一个 agent，priority=1。
- 行程规划请求：先调 event_collection(priority=1)，再调 itinerary_planning(priority=2)；其余信息收集类智能体一律 priority=1。
- priority 数字相同的智能体会并行执行；不同 priority 按顺序批次执行，Priority 2 会使用 Priority 1 的结果。
- 查询"我的/我之前/我去过"优先 memory_query；差旅标准、报销、政策优先 rag_knowledge。
- confidence 低于 {DEFAULT_CONFIDENCE_THRESHOLD:.2f} 时不要调用 skill（agent_schedule 置空）。
- information_query 仅用于明确查询外部事实、实时信息、地点信息、天气、航班、交通、景点、价格等，confidence 至少 {INFORMATION_QUERY_THRESHOLD:.2f}，且查询对象明确。
- 禁止将短输入、寒暄、半句话、无明确查询对象的问题识别为 information_query。
- 寒暄类（chitchat）调用 chitchat skill，priority=1；unclear、unsupported 的 agent_schedule 必须为空。

【Query 改写要求】
将口语化表达标准化，结合对话历史补全省略的信息（如把"那边"指代回填为具体目的地），并重组关键信息；若无需改写则原样保留用户输入。

【Few-shot 反例与正例】
- "你?" → unclear, should_call_skill=false, agent_schedule=[]
- "这个呢" → unclear, should_call_skill=false, agent_schedule=[]
- "在吗" → chitchat, should_call_skill=true, agent_schedule=[chitchat]
- "帮我查明天东京天气" → information_query, should_call_skill=true, agent_schedule=[information_query]
- "餐补标准是多少" → rag_knowledge, should_call_skill=true, agent_schedule=[rag_knowledge]
- "我下周去上海出差，帮我安排两天行程" → event_collection(priority=1) + itinerary_planning(priority=2)

【输出 JSON schema（严格按此结构，key 不要少也不要多）】
{{
  "reasoning": "一句话说明你是如何结合上下文判断意图的",
  "routing": {{"intent": "intent_name", "confidence": 0.0, "reason": "", "should_call_skill": false}},
  "intents": [
    {{"type": "intent_name", "confidence": 0.0, "description": "", "reason": "", "should_call_skill": false}}
  ],
  "key_entities": {{"origin": null, "destination": null, "date": null, "duration": null, "other": null}},
  "rewritten_query": "标准化、补全后的查询内容",
  "agent_schedule": [
    {{"agent_name": "agent_name", "priority": 1, "reason": "", "expected_output": ""}}
  ]
}}"""

        # 调用LLM进行意图识别
        try:
            # 构建符合OpenAI格式的messages
            messages = [
                {"role": "system", "content": "你是一个高级意图识别专家。只输出JSON格式的结果，不要输出其他文本。"},
                {"role": "user", "content": prompt}
            ]
            response = await self.model(messages)
            text = await extract_text_from_response(response)
            result = parse_json_object(text)
            result = validate_intent_result(result)

        except Exception as e:
            logger.error(f"Intent recognition failed: {e}")
            # 识别失败时不允许默认调用 information_query。
            result = {
                "routing": {
                    "intent": "fallback",
                    "confidence": 0.0,
                    "reason": f"意图识别失败: {str(e)}",
                    "should_call_skill": False,
                },
                "reasoning": f"意图识别失败，等待用户澄清。错误: {str(e)}",
                "intents": [
                    {
                        "type": "fallback",
                        "confidence": 0.0,
                        "description": "意图识别失败",
                        "reason": "无法可靠识别用户意图，不调用任何 skill",
                        "should_call_skill": False,
                    }
                ],
                "key_entities": {},
                "rewritten_query": user_query,
                "agent_schedule": [],
                "clarification": "我刚刚没能可靠理解你的需求。你可以再明确一点，是要查差旅政策、规划行程，还是查询某个旅行信息？",
            }

        result = self._apply_routing_guard(result, user_query)

        # 将结果转换为JSON字符串，因为Msg的content必须是字符串
        return Msg(name=self.name, content=json.dumps(result, ensure_ascii=False), role="assistant")

    def _apply_routing_guard(self, result: dict, user_query: str) -> dict:
        routing = result.get("routing") or {}
        intents = result.get("intents") or []
        primary = intents[0] if intents else {}
        intent = routing.get("intent") or primary.get("type") or "unclear"
        confidence = float(routing.get("confidence") or primary.get("confidence") or 0.0)
        reason = routing.get("reason") or primary.get("reason") or result.get("reasoning", "")

        if intent == "information_query":
            info_guard = can_call_information_query(user_query, confidence)
            if not info_guard.should_call_skill:
                return info_guard.to_intention_data(user_query)

        should_call_skill = passes_confidence_gate(intent, confidence)
        if intent in {"unclear", "unsupported", "fallback"}:
            should_call_skill = False

        result["routing"] = {
            "intent": intent,
            "confidence": confidence,
            "reason": reason,
            "should_call_skill": should_call_skill,
        }

        for item in intents:
            item["should_call_skill"] = should_call_skill

        if not should_call_skill:
            result["agent_schedule"] = []
            result.setdefault(
                "clarification",
                "我还不太确定你的意思。你可以再明确一下要查政策、规划行程，还是查询某个旅行信息吗？",
            )

        return result
